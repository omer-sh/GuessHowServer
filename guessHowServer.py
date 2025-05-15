from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import json
import hashlib
import uuid

app = Flask(__name__)

# Database setup
DB_PATH = 'guessHow.db'

def init_db():
    """Initialize the SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if users table exists before modifying it
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    users_table = cursor.fetchone()

    if not users_table:
        # Create new users table with password support
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT,
                salt TEXT
            )
        ''')
    else:
        # Check if password column exists in users table
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        if 'password' not in [col[1] for col in columns]:
            # Add password and salt columns to existing table
            cursor.execute('ALTER TABLE users ADD COLUMN password TEXT')
            cursor.execute('ALTER TABLE users ADD COLUMN salt TEXT')

            # Set default password (hashed with salt) for existing users
            default_salt = uuid.uuid4().hex
            default_password = hashlib.sha256((default_salt + "12345678").encode()).hexdigest()
            cursor.execute('UPDATE users SET password = ?, salt = ?', (default_password, default_salt))

    # Check if name_lists table exists
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='name_lists'")
    lists_table = cursor.fetchone()

    if not lists_table:
        # Create new name_lists table with owner_id and visibility
        cursor.execute('''
            CREATE TABLE name_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_name TEXT NOT NULL,
                names TEXT NOT NULL,  -- JSON string of names array
                owner_id INTEGER,
                is_public INTEGER DEFAULT 1,  -- 1 for public, 0 for private
                FOREIGN KEY (owner_id) REFERENCES users (id)
            )
        ''')
    else:
        # Check if owner_id and is_public columns exist
        cursor.execute("PRAGMA table_info(name_lists)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'owner_id' not in column_names:
            cursor.execute('ALTER TABLE name_lists ADD COLUMN owner_id INTEGER')

        if 'is_public' not in column_names:
            cursor.execute('ALTER TABLE name_lists ADD COLUMN is_public INTEGER DEFAULT 1')

    # Create games table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            list_id INTEGER NOT NULL,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER,
            game_names TEXT NOT NULL,  -- JSON string of selected names
            target_name TEXT NOT NULL,
            FOREIGN KEY (player1_id) REFERENCES users (id),
            FOREIGN KEY (player2_id) REFERENCES users (id),
            FOREIGN KEY (list_id) REFERENCES name_lists (id)
        )
    ''')

    conn.commit()
    conn.close()

# Helper function to generate a random game ID (4 digits)
def generate_game_id():
    return ''.join(random.choices(string.digits, k=4))

# Helper function to hash password
def hash_password(password, salt=None):
    if salt is None:
        salt = uuid.uuid4().hex
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt

@app.route('/users/register', methods=['POST'])
def register_user():
    """
    Endpoint to register a new user for the Guess How game.
    Gets username and optional password in the request body.
    Returns a unique user ID.
    """
    if request.is_json:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username:
            return jsonify({"error": "Username is required"}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Check if username already exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            existing_user = cursor.fetchone()

            if existing_user:
                return jsonify({"error": "Username already exists"}), 409

            # Hash the password
            hashed_password, salt = hash_password(password)

            # Create new user
            cursor.execute("INSERT INTO users (username, password, salt) VALUES (?, ?, ?)",
                          (username, hashed_password, salt))
            conn.commit()
            user_id = cursor.lastrowid

            return jsonify({
                "userId": str(user_id),
                "username": username
            }), 201
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/users/login', methods=['POST'])
def login_user():
    """
    Endpoint to authenticate a user.
    Gets username and password in the request body.
    Returns user ID and username if successful.
    """
    if request.is_json:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get user by username
            cursor.execute("SELECT id, username, password, salt FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()

            if not user:
                return jsonify({"error": "Invalid username or password"}), 401

            # Check password
            hashed_password = hashlib.sha256((user['salt'] + password).encode()).hexdigest()
            if hashed_password != user['password']:
                return jsonify({"error": "Invalid username or password"}), 401

            return jsonify({
                "userId": str(user['id']),
                "username": user['username']
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/namelists', methods=['GET'])
def get_name_lists():
    """
    Endpoint to get all available name lists.
    Optional user_id query param to get private lists owned by the user.
    """
    user_id = request.args.get('userId')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if user_id:
            # Get public lists and private lists owned by the user
            cursor.execute("""
                SELECT id, list_name, names, owner_id, is_public
                FROM name_lists
                WHERE is_public = 1 OR owner_id = ?
            """, (user_id,))
        else:
            # Get only public lists
            cursor.execute("""
                SELECT id, list_name, names, owner_id, is_public
                FROM name_lists
                WHERE is_public = 1
            """)

        name_lists = cursor.fetchall()

        result = []
        for name_list in name_lists:
            result.append({
                "listId": str(name_list['id']),
                "listName": name_list['list_name'],
                "names": json.loads(name_list['names']),
                "ownerId": str(name_list['owner_id']) if name_list['owner_id'] else None,
                "isPublic": bool(name_list['is_public'])
            })

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/namelists', methods=['POST'])
def create_name_list():
    """
    Endpoint to create a new name list.
    Gets listName, names array, and optional isPublic in the request body.
    Returns the created list with its ID.
    """
    if request.is_json:
        data = request.get_json()
        list_name = data.get('listName')
        names = data.get('names', [])
        owner_id = data.get('ownerId')
        is_public = data.get('isPublic', True)

        if not list_name:
            return jsonify({"error": "List name is required"}), 400

        if len(names) < 24:
            return jsonify({"error": "List must contain at least 24 names"}), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            # Store names as JSON string
            names_json = json.dumps(names)

            # Create new name list
            cursor.execute(
                "INSERT INTO name_lists (list_name, names, owner_id, is_public) VALUES (?, ?, ?, ?)",
                (list_name, names_json, owner_id, 1 if is_public else 0)
            )
            conn.commit()
            list_id = cursor.lastrowid

            return jsonify({
                "listId": str(list_id),
                "listName": list_name,
                "names": names,
                "ownerId": owner_id,
                "isPublic": is_public
            }), 201
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/namelists/<list_id>', methods=['PUT'])
def update_name_list(list_id):
    """
    Endpoint to update an existing name list.
    Gets listName, names array, and optional isPublic in the request body.
    Returns the updated list.
    """
    if request.is_json:
        data = request.get_json()
        list_name = data.get('listName')
        names = data.get('names')
        is_public = data.get('isPublic')
        owner_id = data.get('ownerId')

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get the current list
            cursor.execute("SELECT owner_id FROM name_lists WHERE id = ?", (list_id,))
            current_list = cursor.fetchone()

            if not current_list:
                return jsonify({"error": "Name list not found"}), 404

            # Check ownership if owner_id is provided
            if owner_id and str(current_list['owner_id']) != owner_id:
                return jsonify({"error": "You don't have permission to update this list"}), 403

            # Build update query dynamically based on provided fields
            update_parts = []
            params = []

            if list_name:
                update_parts.append("list_name = ?")
                params.append(list_name)

            if names:
                if len(names) < 24:
                    return jsonify({"error": "List must contain at least 24 names"}), 400
                update_parts.append("names = ?")
                params.append(json.dumps(names))

            if is_public is not None:
                update_parts.append("is_public = ?")
                params.append(1 if is_public else 0)

            if update_parts:
                query = "UPDATE name_lists SET " + ", ".join(update_parts) + " WHERE id = ?"
                params.append(list_id)

                cursor.execute(query, params)
                conn.commit()

                # Get updated list details
                cursor.execute("""
                    SELECT id, list_name, names, owner_id, is_public
                    FROM name_lists
                    WHERE id = ?
                """, (list_id,))
                updated_list = cursor.fetchone()

                return jsonify({
                    "listId": str(updated_list['id']),
                    "listName": updated_list['list_name'],
                    "names": json.loads(updated_list['names']),
                    "ownerId": str(updated_list['owner_id']) if updated_list['owner_id'] else None,
                    "isPublic": bool(updated_list['is_public'])
                }), 200
            else:
                return jsonify({"error": "No update fields provided"}), 400
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/namelists/<list_id>', methods=['DELETE'])
def delete_name_list(list_id):
    """
    Endpoint to delete a name list.
    Owner ID is required as query parameter.
    """
    owner_id = request.args.get('ownerId')

    if not owner_id:
        return jsonify({"error": "Owner ID is required"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if list exists and belongs to owner
        cursor.execute("SELECT id FROM name_lists WHERE id = ? AND owner_id = ?", (list_id, owner_id))
        name_list = cursor.fetchone()

        if not name_list:
            return jsonify({"error": "Name list not found or you don't have permission"}), 404

        # Check if list is used in any games
        cursor.execute("SELECT game_id FROM games WHERE list_id = ?", (list_id,))
        games = cursor.fetchone()

        if games:
            return jsonify({"error": "Cannot delete list that is used in games"}), 400

        # Delete the list
        cursor.execute("DELETE FROM name_lists WHERE id = ?", (list_id,))
        conn.commit()

        return jsonify({"success": True, "message": "Name list deleted successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/games', methods=['POST'])
def create_game():
    """
    Endpoint to create a new game.
    Gets player1Id and listId in the request body.
    Returns gameId and the 24 selected names plus target name.
    """
    if request.is_json:
        data = request.get_json()
        player1_id = data.get('player1Id')
        list_id = data.get('listId')

        if not player1_id or not list_id:
            return jsonify({"error": "Player ID and list ID are required"}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Check if player exists
            cursor.execute("SELECT id FROM users WHERE id = ?", (player1_id,))
            player = cursor.fetchone()
            if not player:
                return jsonify({"error": "Player not found"}), 404

            # Check if name list exists and is accessible to player
            cursor.execute("""
                SELECT id, names, is_public, owner_id
                FROM name_lists
                WHERE id = ?
            """, (list_id,))
            name_list = cursor.fetchone()

            if not name_list:
                return jsonify({"error": "Name list not found"}), 404

            # Check permission for private lists
            if not name_list['is_public'] and str(name_list['owner_id']) != player1_id:
                return jsonify({"error": "You don't have access to this name list"}), 403

            # Generate a unique game ID
            game_id = generate_game_id()
            while True:
                cursor.execute("SELECT game_id FROM games WHERE game_id = ?", (game_id,))
                if not cursor.fetchone():
                    break
                game_id = generate_game_id()

            # Select 24 random names from the list
            all_names = json.loads(name_list['names'])
            if len(all_names) < 24:
                return jsonify({"error": "Name list has insufficient names"}), 400

            selected_names = random.sample(all_names, 24)
            # Select a random target name from the selected names
            target_name = random.choice(selected_names)

            # Create the game
            cursor.execute(
                "INSERT INTO games (game_id, list_id, player1_id, game_names, target_name) VALUES (?, ?, ?, ?, ?)",
                (game_id, list_id, player1_id, json.dumps(selected_names), target_name)
            )
            conn.commit()

            return jsonify({
                "gameId": game_id,
                "player1Id": player1_id,
                "gameNames": selected_names,
                "targetName": target_name,
                "listId": list_id
            }), 201
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/games/<game_id>', methods=['GET'])
def join_game(game_id):
    """
    Endpoint to join an existing game.
    Gets gameId in the URL and player2Id as a query parameter.
    Returns the game details including the 24 selected names and target name.
    """
    player2_id = request.args.get('player2Id')

    if not player2_id:
        return jsonify({"error": "Player ID is required"}), 400

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if player exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (player2_id,))
        player = cursor.fetchone()
        if not player:
            return jsonify({"error": "Player not found"}), 404

        # Check if game exists
        cursor.execute("""
            SELECT game_id, player1_id, player2_id, list_id, game_names, target_name
            FROM games
            WHERE game_id = ?
        """, (game_id,))
        game = cursor.fetchone()

        if not game:
            return jsonify({"error": "Game not found"}), 404

        # Update the game with player2
        if game['player2_id']:
            return jsonify({"error": "Game already has two players"}), 409

        cursor.execute(
            "UPDATE games SET player2_id = ? WHERE game_id = ?",
            (player2_id, game_id)
        )
        conn.commit()

        # Get game names
        game_names = json.loads(game['game_names'])

        # Select a new target name for player2 (different from player1's target)
        available_names = [name for name in game_names if name != game['target_name']]
        target_name = random.choice(available_names)

        return jsonify({
            "gameId": game_id,
            "player1Id": game['player1_id'],
            "player2Id": player2_id,
            "gameNames": game_names,
            "targetName": target_name,
            "listId": game['list_id']
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/games/<game_id>/status', methods=['GET'])
def get_game_status(game_id):
    """
    Endpoint to check the status of a game without joining it.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if game exists
        cursor.execute("""
            SELECT game_id, list_id, player1_id, player2_id, game_names, target_name
            FROM games
            WHERE game_id = ?
        """, (game_id,))
        game = cursor.fetchone()

        if not game:
            return jsonify({"error": "Game not found"}), 404

        # Return game details
        game_names = json.loads(game['game_names'])

        return jsonify({
            "gameId": game_id,
            "listId": game['list_id'],
            "player1Id": game['player1_id'],
            "player2Id": game['player2_id'],
            "gameNames": game_names,
            "targetName": game['target_name']
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Initialize the database when the server starts
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=False)