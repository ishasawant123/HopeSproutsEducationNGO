import os
import mysql.connector
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from flask_cors import CORS

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# --- Database Configuration ---
DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'tiger123'),
    'database': os.getenv('MYSQL_DATABASE', 'hop23_db')
}

# --- Database Connection ---
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

# --- Home Route ---
@app.route('/')
def home():
    return render_template('hopesprouts.html')

# --- Error Handler ---
@app.errorhandler(500)
def handle_internal_server_error(e):
    return jsonify(error="An internal server error occurred."), 500

# --- Donations ---
@app.route('/api/process_donation', methods=['POST'])
def process_donation():
    data = request.json
    donor_name = data.get('donor_name', 'Anonymous')
    amount = data.get('amount')
    target = data.get('target')

    if not amount or not target:
        return jsonify({'message': 'Amount and target are required'}), 400

    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db_connection.cursor(buffered=True)
    try:
        target_student_id = None

        # If target is not general → must be a valid student ID (integer)
        if target != 'general':
            try:
                target_student_id = int(target)  # convert string → int
            except ValueError:
                return jsonify({'message': 'Invalid donation target'}), 400

            cursor.execute("SELECT student_id FROM students WHERE student_id = %s", (target_student_id,))
            if not cursor.fetchone():
                return jsonify({'message': 'Invalid donation target'}), 400

        # Insert donation
        insert_query = """
            INSERT INTO donations (donor_name, amount, donation_target, target_student_id) 
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (donor_name, amount, target, target_student_id))
        db_connection.commit()

        # Get invoice ID (last inserted donation)
        invoice_id = cursor.lastrowid

        # Update student donations if targeted
        if target_student_id:
            cursor.execute(
                "UPDATE students SET donations_received = donations_received + %s WHERE student_id = %s",
                (amount, target_student_id)
            )
            db_connection.commit()

        return jsonify({
            'message': 'Donation processed successfully!',
            'invoice_id': invoice_id
        }), 200

    except Exception as e:
        db_connection.rollback()
        return jsonify({'message': f'Error processing donation: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()




# --- Enroll Student ---
@app.route('/api/enroll_student', methods=['POST'])
def enroll_student():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    track = data.get('track')

    if not all([name, email, track]):
        return jsonify({'message': 'Missing required fields'}), 400

    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db_connection.cursor()
    try:
        cursor.execute("INSERT INTO students (name, email, track) VALUES (%s, %s, %s)", (name, email, track))
        db_connection.commit()
        return jsonify({'message': 'Student enrolled successfully!'}), 201
    except mysql.connector.errors.IntegrityError:
        return jsonify({'message': 'Email already exists.'}), 409
    except Exception as e:
        return jsonify({'message': f'Error enrolling student: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()

# --- Volunteer Application ---
@app.route('/api/apply_volunteer', methods=['POST'])
def apply_volunteer():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    skills = data.get('skills')

    if not all([name, email]):
        return jsonify({'message': 'Name and email are required'}), 400

    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db_connection.cursor()
    try:
        cursor.execute("INSERT INTO volunteers (name, email, skills) VALUES (%s, %s, %s)", (name, email, skills))
        db_connection.commit()
        return jsonify({'message': 'Volunteer application submitted successfully!'}), 201
    except mysql.connector.errors.IntegrityError:
        return jsonify({'message': 'Email already exists.'}), 409
    except Exception as e:
        return jsonify({'message': f'Error submitting application: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()

@app.route('/api/dashboard_data', methods=['GET'])
def dashboard_data():
    db = get_db_connection()
    if not db:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db.cursor(dictionary=True)
    try:
        # --- Fetch students ---
        cursor.execute("""
            SELECT student_id, name, progress, last_quiz_score, donations_received, donation_target_amount
            FROM students
        """)
        students = cursor.fetchall()

        # --- Calculate total donations ---
        cursor.execute("SELECT SUM(amount) AS total_donations FROM donations")
        total_donations = cursor.fetchone()['total_donations'] or 0

        # --- Calculate general fund ---
        cursor.execute("SELECT SUM(amount) AS general_fund FROM donations WHERE donation_target = 'general'")
        general_fund = cursor.fetchone()['general_fund'] or 0

        # --- Fetch recent donations (latest 5) ---
        cursor.execute("""
            SELECT donor_name, amount, donation_target, donation_date
            FROM donations
            ORDER BY donation_date DESC
            LIMIT 5
        """)
        recent_donations = cursor.fetchall()

        return jsonify({
            'students': students,
            'total_donations': float(total_donations),
            'general_fund': float(general_fund),
            'recent_donations': recent_donations
        })
    except Exception as e:
        return jsonify({'message': f'Error fetching dashboard data: {str(e)}'}), 500
    finally:
        cursor.close()
        db.close()



# --- Leaderboard Data Endpoint ---
@app.route('/api/leaderboard_data', methods=['GET'])
def leaderboard_data():
    db = get_db_connection()
    if not db:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db.cursor(dictionary=True)
    try:
        # --- Top 5 donors ---
        cursor.execute("""
            SELECT donor_name AS name, SUM(amount) AS total_donated
            FROM donations
            GROUP BY donor_name
            ORDER BY total_donated DESC
            LIMIT 5
        """)
        donors = cursor.fetchall()

        # --- Top 5 volunteers ---
        cursor.execute("""
            SELECT name, points
            FROM volunteers
            ORDER BY points DESC
            LIMIT 5
        """)
        volunteers = cursor.fetchall()

        return jsonify({
            'donors': donors,
            'volunteers': volunteers
        })
    except Exception as e:
        return jsonify({'message': f'Error fetching leaderboard data: {str(e)}'}), 500
    finally:
        cursor.close()
        db.close()



# --- Add Story ---
@app.route('/api/add_story', methods=['POST'])
def add_story():
    data = request.json
    name = data.get('name', '').strip()
    title = data.get('title', '').strip()
    text = data.get('text', '').strip()

    if not all([name, title, text]):
        return jsonify({'message': 'All fields are required!'}), 400

    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db_connection.cursor()
    try:
        insert_query = "INSERT INTO stories (name, title, story_text) VALUES (%s, %s, %s)"
        cursor.execute(insert_query, (name, title, text))
        db_connection.commit()
        return jsonify({'message': 'Thank you for sharing your story!'}), 201
    except Exception as e:
        db_connection.rollback()
        return jsonify({'message': f'Error adding story: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()

# --- Get Stories ---
@app.route('/api/stories', methods=['GET'])
def get_stories():
    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'message': 'Database connection failed'}), 500

    cursor = db_connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT name, title, story_text, submission_date FROM stories ORDER BY submission_date DESC")
        stories = cursor.fetchall()
        return jsonify(stories), 200
    except Exception as e:
        return jsonify({'message': f'Error fetching stories: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()


# --- Contact Form API Endpoint ---
@app.route('/api/send_contact', methods=['POST'])
def send_contact():
    """
    Receives contact form data via a POST request, validates it, and
    inserts it into the 'contact' table in the database.
    """
    try:
        # Get JSON data from the request body
        data = request.json
        name = data.get('name')
        email = data.get('email')
        message = data.get('message')

        # Basic validation to ensure all fields are present
        if not all([name, email, message]):
            return jsonify({'message': 'Missing required fields'}), 400

        db_connection = get_db_connection()
        if not db_connection:
            return jsonify({'message': 'Database connection failed'}), 500

        cursor = db_connection.cursor()
        try:
            # SQL query to insert data. Using placeholders (%s) prevents SQL injection.
            insert_query = "INSERT INTO contact (name, email, message) VALUES (%s, %s, %s)"
            cursor.execute(insert_query, (name, email, message))
            db_connection.commit()
            
            # Return a success message with a 201 status code (Created)
            return jsonify({'message': 'Message sent successfully!'}), 201
        except mysql.connector.Error as db_err:
            # Log the specific database error for debugging
            print(f"Database error: {db_err}")
            db_connection.rollback()
            return jsonify({'message': f'Error sending message: {str(db_err)}'}), 500
        finally:
            cursor.close()
            db_connection.close()

    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"Unexpected error: {e}")
        return jsonify({'message': f'An unexpected error occurred: {str(e)}'}), 500

# --- Get single student by ID ---
@app.route('/api/student/<int:student_id>', methods=['GET'])
def get_student(student_id):
    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = db_connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT student_id, name, email, track, last_quiz_score, progress FROM students WHERE student_id = %s", (student_id,))
        student = cursor.fetchone()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        return jsonify(student), 200
    except Exception as e:
        return jsonify({'error': f'Error fetching student data: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()

# --- Submit Quiz Score ---
@app.route('/api/submit_quiz', methods=['POST'])
def submit_quiz():
    data = request.json
    student_id = data.get('student_id')
    score = data.get('score')
    total_questions = data.get('total_questions')

    if not student_id or score is None or total_questions is None:
        return jsonify({'error': 'Missing student_id, score, or total_questions'}), 400

    db_connection = get_db_connection()
    if not db_connection:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = db_connection.cursor()
    try:
        # Update student progress and last quiz score
        cursor.execute("""
            UPDATE students 
            SET last_quiz_score = %s, quiz_attempts = quiz_attempts + 1, progress = progress + %s
            WHERE student_id = %s
        """, (score, score, student_id))

        db_connection.commit()
        return jsonify({'message': f'Score saved successfully for student ID {student_id}'}), 200

    except Exception as e:
        db_connection.rollback()
        return jsonify({'error': f'Error saving quiz score: {str(e)}'}), 500
    finally:
        cursor.close()
        db_connection.close()



# --- Run App ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)

