from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import random
import string

app = Flask(__name__)

# MongoDB setup
client = MongoClient('')
db = client['GuessHow']

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
        
        # Check if username already exists
        existing_user = db.users.find_one({"username": username})
        if existing_user:
            return jsonify({"error": "Username already exists"}), 409
        
        # Create new user
        user = {
            "username": username
        }
        
        result = db.users.insert_one(user)
        user_id = str(result.inserted_id)
        
        return jsonify({
            "userId": user_id,
            "username": username
        }), 201
    else:
        return jsonify({"error": "Request must be JSON"}), 415

@app.route('/namelists', methods=['GET'])
def get_name_lists():
    """
    Endpoint to get all available name lists.
    """
    name_lists = db.name_lists.find()
    result = []
    
    for name_list in name_lists:
        result.append({
            "listId": str(name_list['_id']),
            "listName": name_list['listName'],
            "names": name_list['names']
        })
        
    return jsonify(result), 200

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
        
        # Create new name list
        name_list = {
            "listName": list_name,
            "names": names
        }
        
        result = db.name_lists.insert_one(name_list)
        list_id = str(result.inserted_id)
        
        return jsonify({
            "listId": list_id,
            "listName": list_name,
            "names": names
        }), 201
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
            
        # Check if player exists
        player = db.users.find_one({"_id": ObjectId(player1_id)})
        if not player:
            return jsonify({"error": "Player not found"}), 404
            
        # Check if name list exists
        name_list = db.name_lists.find_one({"_id": ObjectId(list_id)})
        if not name_list:
            return jsonify({"error": "Name list not found"}), 404
            
        # Generate a unique game ID
        while True:
            game_id = generate_game_id()
            if not db.games.find_one({"gameId": game_id}):
                break
                
        # Select 24 random names from the list
        all_names = name_list['names']
        if len(all_names) < 24:
            return jsonify({"error": "Name list has insufficient names"}), 400
            
        selected_names = random.sample(all_names, 24)
        # Select a random target name from the selected names
        target_name = random.choice(selected_names)
        
        # Create the game
        game = {
            "gameId": game_id,
            "listId": list_id,
            "player1Id": player1_id,
            "player2Id": None,
            "gameNames": selected_names,
            "targetName": target_name
        }
        
        db.games.insert_one(game)
        
        return jsonify({
            "gameId": game_id,
            "player1Id": player1_id,
            "gameNames": selected_names,
            "targetName": target_name
        }), 201
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
        
    # Check if player exists
    player = db.users.find_one({"_id": ObjectId(player2_id)})
    if not player:
        return jsonify({"error": "Player not found"}), 404
        
    # Check if game exists
    game = db.games.find_one({"gameId": game_id})
    if not game:
        return jsonify({"error": "Game not found"}), 404
        
    # Update the game with player2
    if game.get('player2Id'):
        return jsonify({"error": "Game already has two players"}), 409
        
    db.games.update_one(
        {"gameId": game_id},
        {"$set": {"player2Id": player2_id}}
    )
    
    # Select a new target name for player2 (different from player1's target)
    available_names = game['gameNames']
    target_name = random.choice([name for name in available_names if name != game['targetName']])
    
    return jsonify({
        "gameId": game_id,
        "player1Id": game['player1Id'],
        "player2Id": player2_id,
        "gameNames": game['gameNames'],
        "targetName": target_name
    }), 200

def myApp(environ, start_response):
    app.run(host='0.0.0.0', port=4000)

if __name__ == '__main__':
    myApp(None, None)
    # For direct running:
    # app.run(host='0.0.0.0', port=4000, ssl_context=('cert.pem', 'key.pem'))
