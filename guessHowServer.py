from flask import Flask, request, jsonify
import sqlite3
import random
import string
import os
import json

app = Flask(__name__)

# Database setup
DB_PATH = 'guessHow.db'

def init_db():
    """Initialize the SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create name_lists table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS name_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_name TEXT NOT NULL,
            names TEXT NOT NULL  -- JSON string of names array
        )
    ''')
    
    # Create games table
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

@app.route('/users/register', methods=['POST'])
def register_user():
    """
    Endpoint to register a new user for the Guess How game.
    Gets username in the request body.
    Returns a unique user ID.
    """
    if request.is_json:
        data = request.get_json()
        username = data.get('username')
        
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
            
            # Create new user
            cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
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

@app.route('/namelists', methods=['GET'])
def get_name_lists():
    """
    Endpoint to get all available name lists.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, list_name, names FROM name_lists")
        name_lists = cursor.fetchall()
        
        result = []
        for name_list in name_lists:
            result.append({
                "listId": str(name_list['id']),
                "listName": name_list['list_name'],
                "names": json.loads(name_list['names'])
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
    Gets listName and names array in the request body.
    Returns the created list with its ID.
    """
    if request.is_json:
        data = request.get_json()
        list_name = data.get('listName')
        names = data.get('names', [])
        
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
                "INSERT INTO name_lists (list_name, names) VALUES (?, ?)", 
                (list_name, names_json)
            )
            conn.commit()
            list_id = cursor.lastrowid
            
            return jsonify({
                "listId": str(list_id),
                "listName": list_name,
                "names": names
            }), 201
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()
    else:
        return jsonify({"error": "Request must be JSON"}), 415

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
                
            # Check if name list exists
            cursor.execute("SELECT id, names FROM name_lists WHERE id = ?", (list_id,))
            name_list = cursor.fetchone()
            if not name_list:
                return jsonify({"error": "Name list not found"}), 404
                
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
                "targetName": target_name
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
        cursor.execute("SELECT game_id, player1_id, player2_id, game_names, target_name FROM games WHERE game_id = ?", 
                     (game_id,))
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
            "targetName": target_name
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Initialize the database when the server starts
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=False)