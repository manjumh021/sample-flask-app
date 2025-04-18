from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from db import get_db_connection, init_db
import logging
from logging.handlers import RotatingFileHandler
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from marshmallow import Schema, fields, validate, ValidationError

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure app
app.config['JSON_SORT_KEYS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-dev-key')
app.config['ENV'] = os.getenv('FLASK_ENV', 'production')
app.config['DEBUG'] = os.getenv('FLASK_ENV', 'production') == 'development'

# Fix for proper IP handling behind proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/api.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Flask API startup')

# Define validation schemas
class ItemSchema(Schema):
    """Schema for validating item data"""
    name = fields.String(required=True, validate=validate.Length(min=1, max=255), 
                         error_messages={"required": "Name is required."})
    description = fields.String(validate=validate.Length(max=1000), missing="")

class ItemUpdateSchema(Schema):
    """Schema for validating item update data"""
    name = fields.String(validate=validate.Length(min=1, max=255))
    description = fields.String(validate=validate.Length(max=1000))

# Initialize the database on startup
with app.app_context():
    init_db()

# Route handlers
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'flask-mysql-api'})

@app.route('/api/items', methods=['GET'])
def get_items():
    """Get all items from the database"""
    try:
        # Optional query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)  # Limit to 100 max
        name_filter = request.args.get('name', '')
        
        # Validate pagination parameters
        if page < 1:
            return jsonify({'error': 'Page must be a positive integer'}), 400
        if per_page < 1:
            return jsonify({'error': 'Per_page must be a positive integer'}), 400
            
        offset = (page - 1) * per_page
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Apply filters if provided
        if name_filter:
            cursor.execute('SELECT * FROM items WHERE name LIKE %s LIMIT %s OFFSET %s', 
                          (f'%{name_filter}%', per_page, offset))
        else:
            cursor.execute('SELECT * FROM items LIMIT %s OFFSET %s', (per_page, offset))
            
        items = cursor.fetchall()
        
        # Get total count for pagination info
        if name_filter:
            cursor.execute('SELECT COUNT(*) as count FROM items WHERE name LIKE %s', (f'%{name_filter}%',))
        else:
            cursor.execute('SELECT COUNT(*) as count FROM items')
            
        total_count = cursor.fetchone()['count']
        cursor.close()
        conn.close()
        
        return jsonify({
            'items': items,
            'pagination': {
                'total_items': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page
            }
        })
    except Exception as e:
        app.logger.error(f'Error getting items: {str(e)}')
        return jsonify({'error': 'Failed to fetch items'}), 500

@app.route('/api/items/<int:item_id>', methods=['GET'])
def get_item(item_id):
    """Get a specific item by ID"""
    try:
        # Validate item_id
        if item_id <= 0:
            return jsonify({'error': 'Item ID must be a positive integer'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM items WHERE id = %s', (item_id,))
        item = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if item:
            return jsonify({'item': item})
        return jsonify({'error': 'Item not found'}), 404
    except Exception as e:
        app.logger.error(f'Error getting item {item_id}: {str(e)}')
        return jsonify({'error': 'Failed to fetch item'}), 500

@app.route('/api/items', methods=['POST'])
def create_item():
    """Create a new item"""
    if not request.is_json:
        return jsonify({'error': 'Request body must be JSON'}), 400
        
    data = request.get_json()
    
    # Validate input data using schema
    try:
        item_schema = ItemSchema()
        validated_data = item_schema.load(data)
    except ValidationError as err:
        return jsonify({'error': 'Validation error', 'details': err.messages}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO items (name, description) VALUES (%s, %s)',
            (validated_data['name'], validated_data['description'])
        )
        conn.commit()
        new_item_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({'id': new_item_id, 'message': 'Item created successfully'}), 201
    except Exception as e:
        app.logger.error(f'Error creating item: {str(e)}')
        return jsonify({'error': 'Failed to create item'}), 500

@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    """Update an existing item"""
    # Validate item_id
    if item_id <= 0:
        return jsonify({'error': 'Item ID must be a positive integer'}), 400
        
    if not request.is_json:
        return jsonify({'error': 'Request body must be JSON'}), 400
        
    data = request.get_json()
    
    # Validate input data using schema
    try:
        item_update_schema = ItemUpdateSchema()
        validated_data = item_update_schema.load(data)
        
        # Ensure at least one field is being updated
        if not validated_data:
            return jsonify({'error': 'No valid fields to update'}), 400
    except ValidationError as err:
        return jsonify({'error': 'Validation error', 'details': err.messages}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if item exists
        cursor.execute('SELECT id FROM items WHERE id = %s', (item_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        # Update the item
        update_fields = []
        params = []
        
        if 'name' in validated_data:
            update_fields.append('name = %s')
            params.append(validated_data['name'])
        
        if 'description' in validated_data:
            update_fields.append('description = %s')
            params.append(validated_data['description'])
        
        query = f"UPDATE items SET {', '.join(update_fields)} WHERE id = %s"
        params.append(item_id)
        
        cursor.execute(query, tuple(params))
        conn.commit()
        
        # Check if any rows were affected (should always be true at this point)
        rows_affected = cursor.rowcount
        cursor.close()
        conn.close()
        
        if rows_affected > 0:
            return jsonify({'message': 'Item updated successfully'})
        else:
            # This should rarely happen given our earlier check
            return jsonify({'message': 'No changes applied to item'}), 200
            
    except Exception as e:
        app.logger.error(f'Error updating item {item_id}: {str(e)}')
        return jsonify({'error': 'Failed to update item'}), 500

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    """Delete an item"""
    # Validate item_id
    if item_id <= 0:
        return jsonify({'error': 'Item ID must be a positive integer'}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if item exists
        cursor.execute('SELECT id FROM items WHERE id = %s', (item_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        cursor.execute('DELETE FROM items WHERE id = %s', (item_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Item deleted successfully'})
    except Exception as e:
        app.logger.error(f'Error deleting item {item_id}: {str(e)}')
        return jsonify({'error': 'Failed to delete item'}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(415)
def unsupported_media_type(error):
    return jsonify({'error': 'Unsupported media type'}), 415

@app.errorhandler(500)
def internal_server_error(error):
    app.logger.error(f'Server error: {str(error)}')
    return jsonify({'error': 'Internal server error'}), 500

# Custom error handler for JSON parsing errors
@app.errorhandler(400)
def bad_request(error):
    # Handle JSON decode errors specifically
    if "Failed to decode JSON object" in str(error):
        return jsonify({'error': 'Invalid JSON in request body'}), 400
    return jsonify({'error': str(error)}), 400

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)