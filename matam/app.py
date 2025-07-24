"""
Flask web application for face matching, gallery management, and admin dashboard.
Handles user requests, face matching, email delivery, and admin operations.
"""
import os
from flask import Flask, render_template, request, send_from_directory, jsonify, redirect, url_for, session, flash, make_response
import subprocess
import shutil
from flask_mail import Mail, Message
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from supabase import create_client, Client
from passlib.hash import bcrypt
from datetime import timedelta, datetime
import zipfile
import tempfile
import uuid
import threading
import time
import base64

load_dotenv()

app = Flask(__name__)

MATCHED_FOLDER = 'static/matched'
GALLERY_FOLDER = 'static/gallery'
EMAIL_FLAG_FILE = 'stored_email.txt'
EMAIL_SENT_FLAG = 'email_sent.flag'
UPLOAD_TMP_DIR = 'tmp_frames'
os.makedirs(UPLOAD_TMP_DIR, exist_ok=True)
# Clean up all old temp frame folders on startup
for folder in os.listdir(UPLOAD_TMP_DIR):
    folder_path = os.path.join(UPLOAD_TMP_DIR, folder)
    if os.path.isdir(folder_path):
        shutil.rmtree(folder_path, ignore_errors=True)

# --- Mail configuration ---
mail_server = os.getenv('MAIL_SERVER')
mail_port = os.getenv('MAIL_PORT')
mail_use_tls = os.getenv('MAIL_USE_TLS')
mail_username = os.getenv('MAIL_USERNAME')
mail_password = os.getenv('MAIL_PASSWORD')
mail_default_sender = os.getenv('MAIL_USERNAME')

if not all([mail_server, mail_port, mail_use_tls, mail_username, mail_password]):
    raise RuntimeError('Missing one or more required mail environment variables.')

if mail_port is None:
    raise RuntimeError('MAIL_PORT environment variable is missing.')
app.config['MAIL_PORT'] = int(mail_port)

app.config['MAIL_SERVER'] = mail_server
app.config['MAIL_USE_TLS'] = mail_use_tls == 'True'
app.config['MAIL_USERNAME'] = mail_username
app.config['MAIL_PASSWORD'] = mail_password
app.config['MAIL_DEFAULT_SENDER'] = mail_default_sender

mail = Mail()

# --- Supabase Setup ---
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError('Missing SUPABASE_URL or SUPABASE_KEY environment variable.')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

mail.init_app(app)

app.secret_key = os.getenv('SECRET_KEY')  # Needed for session
app.permanent_session_lifetime = timedelta(hours=2)

# --- Admin Authentication ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

def is_admin_logged_in():
    """
    Check if the current session is authenticated as admin.
    Returns:
        bool: True if admin is logged in, False otherwise.
    """
    return session.get('admin_logged_in', False)

@app.route('/supersecretadmin/login', methods=['GET', 'POST'])
def admin_login():
    """
    Admin login route. Handles GET (show login form) and POST (process login).
    Returns:
        Response: Redirects to dashboard on success, or renders login page with error on failure.
    """
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    # Removed the check for '?show=1' so login page always shows
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = None
        try:
            admin = supabase.table("admins").select("username,password_hash").eq("username", username).single().execute().data
        except Exception as e:
            # If no admin found, show a friendly message
            flash('You do not have access.', 'danger')
            return render_template('admin_login.html')
        if admin and password and admin["password_hash"]:
            session.permanent = True
            if bcrypt.verify(password, admin["password_hash"]):
                session['admin_logged_in'] = True
                session['admin_username'] = username
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid credentials', 'danger')
        else:
            flash('Invalid credentials', 'danger')
    return render_template('admin_login.html')

@app.route('/supersecretadmin/dashboard')
def admin_dashboard():
    """
    Admin dashboard route. Shows gallery images and credential status.
    Returns:
        Response: Renders the admin dashboard template.
    """
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    credentials_exists = os.path.exists(os.path.join(os.path.dirname(__file__), 'credentials.json'))
    gallery_folder = os.path.join('static', 'gallery')
    gallery_images = []
    if os.path.exists(gallery_folder):
        gallery_images = [f for f in os.listdir(gallery_folder) if not f.startswith('.')]
    response = make_response(render_template('admin_dashboard.html', credentials_exists=credentials_exists, gallery_images=gallery_images))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/supersecretadmin/logout')
def admin_logout():
    """
    Logs out the admin by clearing the session.
    Returns:
        Response: Redirects to the admin login page.
    """
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/')
def index():
    """
    User-facing index route. Renders the main page for face capture and matching.
    Returns:
        Response: Renders the index.html template.
    """
    return render_template('index.html')

def process_pending_request_async():
    """
    Background thread to process the most recent pending user request:
    - Zips matched images
    - Uploads to Supabase Storage
    - Sends email with download link
    - Updates request status
    """
    def worker():
        with app.app_context():
            from time import sleep
            sleep(2)
            pending = supabase.table('user_requests').select('*').eq('status', 'pending').order('created_at', desc=True).limit(1).execute().data
            if not pending:
                print('DEBUG: No pending user_requests found')
                return
            req = pending[0]
            request_id = req['id']
            email = req['email']
            MATCHED_FOLDER = 'static/matched'
            matched_files = [f for f in os.listdir(MATCHED_FOLDER) if f.startswith('clean_')]
            print('DEBUG: [async] matched_files:', matched_files)
            if not matched_files:
                print('DEBUG: [async] No matched files found')
                supabase.table('user_requests').update({'status': 'error'}).eq('id', request_id).execute()
                return
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
                with zipfile.ZipFile(tmp_zip, 'w') as zipf:
                    for idx, file_path in enumerate([os.path.join(MATCHED_FOLDER, f) for f in matched_files], 1):
                        ext = os.path.splitext(file_path)[1]
                        new_name = f"matched_{idx}{ext}"
                        zipf.write(file_path, new_name)
                zip_path = tmp_zip.name
            print('DEBUG: [async] Zip created at', zip_path)
            bucket_name = "matched-results"
            zip_filename = f"matched_{email.replace('@', '_').replace('.', '_')}_{request_id}.zip"
            with open(zip_path, "rb") as f:
                upload_response = supabase.storage.from_(bucket_name).upload(
                    zip_filename, f, {"content-type": "application/zip", "x-upsert": "true"}
                )
            print('DEBUG: [async] Uploaded zip, response:', upload_response)
            public_url = supabase.storage.from_(bucket_name).get_public_url(zip_filename)
            print('DEBUG: [async] public_url:', public_url)
            msg = Message("Face Match Results", recipients=[email])
            msg.body = f"\U0001F4C1 Your matched images are here:\n\n{public_url}\n\nThis link will expire in 1 hour."
            mail.send(msg)
            print('DEBUG: [async] Email sent')
            now = datetime.utcnow().isoformat()
            supabase.table('user_requests').update({
                'zip_url': public_url,
                'status': 'done',
                'matched_files': matched_files,
                'zip_uploaded_at': now
            }).eq('id', request_id).execute()
            print('DEBUG: [async] Updated user_request row to done')
            os.remove(zip_path)
            print('DEBUG: [async] Removed temp zip')
    threading.Thread(target=worker, daemon=True).start()

# --- Scheduled cleanup for expired zips ---
def cleanup_expired_zips():
    """
    Periodically checks for expired zip files in Supabase Storage (older than 1 hour) and deletes them.
    Updates the corresponding user_requests row to 'expired'.
    """
    with app.app_context():
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        expired = supabase.table('user_requests').select('*').neq('zip_url', None).execute().data
        for req in expired:
            uploaded_at = req.get('zip_uploaded_at')
            if uploaded_at:
                try:
                    uploaded_time = datetime.fromisoformat(uploaded_at)
                except Exception:
                    continue
                if uploaded_time < cutoff:
                    zip_url = req['zip_url']
                    filename = zip_url.split('/')[-1].split('?')[0]
                    try:
                        supabase.storage.from_('matched-results').remove(filename)
                        print(f"Deleted expired zip: {filename}")
                    except Exception as e:
                        print(f"Error deleting zip {filename}: {e}")
                    supabase.table('user_requests').update({'zip_url': None, 'status': 'expired'}).eq('id', req['id']).execute()

def start_cleanup_scheduler():
    """
    Starts a background thread to periodically run cleanup_expired_zips every hour.
    """
    def loop():
        while True:
            cleanup_expired_zips()
            time.sleep(3600)  # Run every hour
    threading.Thread(target=loop, daemon=True).start()

# Start the scheduler when app starts
start_cleanup_scheduler()

def cleanup_old_gallery_images():
    """
    Background thread to delete gallery images older than 30 days from the static/gallery folder.
    """
    while True:
        now = time.time()
        cutoff = now - 30 * 24 * 60 * 60  # 30 days in seconds
        deleted = 0
        if not os.path.exists(GALLERY_FOLDER):
            print("[INFO] Gallery folder does not exist. Admin has to upload gallery folder.")
            time.sleep(24 * 60 * 60)  # Wait a day before checking again
            continue
        for fname in os.listdir(GALLERY_FOLDER):
            fpath = os.path.join(GALLERY_FOLDER, fname)
            if os.path.isfile(fpath):
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    deleted += 1
        if deleted:
            print(f"🧹 Deleted {deleted} old gallery images.")
        time.sleep(24 * 60 * 60)  # Run once per day

# Start the gallery cleanup scheduler in background
threading.Thread(target=cleanup_old_gallery_images, daemon=True).start()

# Temporary in-memory store for uploaded frames
uploaded_frames_store = {}

@app.route('/upload_frames', methods=['POST'])
def upload_frames():
    """
    Receives frames (base64 images) from the frontend, stores them on disk under a request_id. Does NOT start matching yet.
    """
    data = request.get_json()
    frames = data.get('frames', [])
    request_id = data.get('request_id')
    print(f"[DEBUG] Received {len(frames)} frames from frontend for request_id={request_id}.")
    if not frames or len(frames) < 1:
        print("[ERROR] No frames received.")
        return jsonify(status='error', message='No frames received.'), 400
    if not request_id:
        print("[ERROR] No request_id provided.")
        return jsonify(status='error', message='No request_id provided.'), 400
    # Store frames on disk
    req_dir = os.path.join(UPLOAD_TMP_DIR, request_id)
    os.makedirs(req_dir, exist_ok=True)
    for idx, frame in enumerate(frames):
        if frame.startswith('data:image'):
            header, b64data = frame.split(',', 1)
        else:
            b64data = frame
        file_path = os.path.join(req_dir, f'frame_{idx+1:03d}.jpg')
        with open(file_path, 'wb') as f:
            f.write(base64.b64decode(b64data))
    print(f"[DEBUG] Frame upload complete for request_id= {request_id}")
    return jsonify(status='ok')

@app.route('/store_email', methods=['POST'])
def store_email():
    """
    Stores the user's email, request_id, and event_name, then starts the matching process using the frames for that request_id and event's gallery.
    """
    print('DEBUG: /store_email called')
    data = request.get_json()
    email = data.get('email')
    request_id = data.get('request_id')
    event_name = data.get('event_name')
    print('DEBUG: email received:', email, 'request_id:', request_id, 'event_name:', event_name)
    if not email or not request_id or not event_name:
        print('DEBUG: Missing email, request_id, or event_name')
        return jsonify(status='error', message='Missing email, request_id, or event_name.')
    # Insert user request into Supabase
    try:
        supabase.table('user_requests').insert({
            'id': request_id,
            'email': email,
            'status': 'pending',
            'matched_files': [],
            'event_name': event_name
        }).execute()
        print('DEBUG: Inserted user_request row')
        # Call process_user_request in a background thread, passing the request_id, email, and event_name
        import threading
        def run_matching():
            from match_faces import run_face_matching
            import cv2
            import numpy as np
            import shutil
            # Load frames from disk
            req_dir = os.path.join(UPLOAD_TMP_DIR, request_id)
            if not os.path.exists(req_dir):
                print(f"[ERROR] No frames found on disk for request_id={request_id}")
                supabase.table('user_requests').update({'status': 'no_frames'}).eq('id', request_id).execute()
                return
            # Use the selected event's gallery folder
            event_gallery_folder = os.path.join(GALLERY_FOLDER, event_name)
            match_count = run_face_matching(req_dir, event_gallery_folder)
            # Clean up temp frames
            shutil.rmtree(req_dir, ignore_errors=True)
            if match_count == 0:
                print("[ERROR] No face detected or no matches found.")
                supabase.table('user_requests').update({'status': 'no_face'}).eq('id', request_id).execute()
                return
            # Continue with the rest of the pipeline (email, etc.)
            process_pending_request_async()
        threading.Thread(target=run_matching, daemon=True).start()
    except Exception as e:
        print('DEBUG: Exception occurred:', e)
        return jsonify(status='error', message=str(e))
    print('DEBUG: /store_email completed successfully')
    return jsonify(status='ok', request_id=request_id)

@app.route('/status', methods=['GET', 'POST'])
def status():
    """
    Returns the status and zip_url for a given user request.
    Accepts request_id via GET or POST.
    Returns:
        JSON: {status: ..., zip_url: ..., error_message: ...} or error message.
    """
    if request.method == 'POST':
        request_id = request.get_json().get('request_id')
    else:
        request_id = request.args.get('request_id')
    if not request_id:
        return jsonify(status='error', message='Missing request_id'), 400
    row = supabase.table('user_requests').select('*').eq('id', request_id).single().execute().data
    if not row:
        return jsonify(status='error', message='Request not found')
    return jsonify(
        status=row['status'],
        zip_url=row.get('zip_url'),
        error_message=row.get('error_message', '')
    )

# Optionally, you can remove or disable the /send_email endpoint, or keep it for admin/manual use only.


@app.route('/clear_gallery', methods=['POST'])
def clear_gallery():
    """
    Clears the gallery folder by removing all files.
    Returns:
        JSON: {status: 'ok'} on success, or error message.
    """
    try:
        if os.path.exists(GALLERY_FOLDER):
            shutil.rmtree(GALLERY_FOLDER)
        os.makedirs(GALLERY_FOLDER, exist_ok=True)
        print("🧹 Gallery cleared.")
        return jsonify(status='ok')
    except Exception as e:
        print("❌ Clear gallery error:", e)
        return jsonify(status='error', message=str(e))

@app.route('/reset', methods=['POST'])
def reset():
    """
    Resets the application state by clearing matched and gallery folders.
    Returns:
        JSON: {status: 'ok'} on success, or error message.
    """
    try:
        if os.path.exists(MATCHED_FOLDER):
            shutil.rmtree(MATCHED_FOLDER)
        os.makedirs(MATCHED_FOLDER, exist_ok=True)

        if os.path.exists(EMAIL_FLAG_FILE):
            os.remove(EMAIL_FLAG_FILE)

        if os.path.exists(EMAIL_SENT_FLAG):
            os.remove(EMAIL_SENT_FLAG)

        return jsonify(status='ok')
    except Exception as e:
        print("❌ Reset error:", e)
        return jsonify(status='error', message=str(e))

# Remove add_admin, list_admins, delete_admin, and edit_admin routes

@app.route('/supersecretadmin/change_password', methods=['POST'])
def change_password():
    """
    Admin changes their password.
    Returns:
        Response: Redirects to admin dashboard on success, or back to dashboard with error.
    """
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    admin_username = session.get('admin_username')
    # Fetch admin from Supabase
    admin = None
    try:
        admin = supabase.table("admins").select("username,password_hash").eq("username", admin_username).single().execute().data
    except Exception as e:
        flash('Error fetching admin.', 'danger')
        return redirect(url_for('admin_dashboard'))
    if not admin or not bcrypt.verify(current_password, admin["password_hash"]):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('admin_dashboard'))
    # Update password
    new_hash = bcrypt.hash(new_password)
    try:
        supabase.table("admins").update({"password_hash": new_hash}).eq("username", admin_username).execute()
        flash('Password changed successfully.', 'success')
    except Exception as e:
        flash('Failed to change password.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/supersecretadmin/list_user_logs')
def list_user_logs():
    """
    Lists the last 100 user requests for admin monitoring.
    Returns:
        JSON: List of user requests.
    """
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))
    logs = supabase.table('user_requests').select('id,email,created_at,status,matched_files,zip_url').order('created_at', desc=True).limit(100).execute().data
    return jsonify(logs)

@app.route('/admin/upload_gallery', methods=['POST'])
def admin_upload_gallery():
    """
    (Admin) Handles file uploads to the gallery.
    Supports zip file upload or multiple file uploads, organized by event name.
    Returns:
        JSON: {status: 'ok'} on success, or error message.
    """
    if not is_admin_logged_in():
        return jsonify(status='error', message='Not authorized'), 403
    try:
        event_name = request.form.get('event_name') or request.values.get('event_name')
        if not event_name:
            return jsonify(status='error', message='Event name is required.')
        event_name = secure_filename(event_name.strip())
        event_gallery_folder = os.path.join(GALLERY_FOLDER, event_name)
        os.makedirs(event_gallery_folder, exist_ok=True)

        # Check for zip upload
        if 'gallery_zip' in request.files:
            zip_file = request.files['gallery_zip']
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
                zip_file.save(tmp_zip)
                tmp_zip_path = tmp_zip.name
            with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(event_gallery_folder)
            os.remove(tmp_zip_path)
            return jsonify(status='ok')

        # Check for folder upload (multiple files)
        files = request.files.getlist('gallery_files')
        ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        if files:
            for f in files:
                filename = os.path.basename(f.filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ALLOWED_EXTENSIONS:
                    continue  # Skip non-image files
                unique_name = f"gallery_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
                dest_path = os.path.join(event_gallery_folder, unique_name)
                f.save(dest_path)
            return jsonify(status='ok')

        return jsonify(status='error', message='No files uploaded.')
    except Exception as e:
        print('❌ Gallery upload error:', e)
        return jsonify(status='error', message=str(e))

@app.route('/admin/list_gallery_images')
def admin_list_gallery_images():
    """
    (Admin) Lists all images in the gallery folder, event-wise.
    Query param: event (optional) - if provided, lists images for that event; else, lists available events.
    Returns:
        JSON: {status: 'ok', events: [...]} or {status: 'ok', images: [...], event: ...}
    """
    if not is_admin_logged_in():
        return jsonify(status='error', message='Not authorized'), 403
    event = request.args.get('event')
    try:
        if event:
            event_folder = os.path.join(GALLERY_FOLDER, event)
            if not os.path.exists(event_folder) or not os.path.isdir(event_folder):
                return jsonify(status='error', message='Event not found')
            images = [f for f in os.listdir(event_folder)
                      if os.path.isfile(os.path.join(event_folder, f)) and f.lower().endswith((
                          '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))]
            return jsonify(status='ok', images=images, event=event)
        else:
            events = [d for d in os.listdir(GALLERY_FOLDER)
                      if os.path.isdir(os.path.join(GALLERY_FOLDER, d)) and not d.startswith('.')]
            return jsonify(status='ok', events=events)
    except Exception as e:
        return jsonify(status='error', message=str(e))

@app.route('/admin/delete_gallery_image', methods=['POST'])
def admin_delete_gallery_image():
    """
    (Admin) Deletes a specific image from the gallery.
    Returns:
        JSON: {status: 'ok'} on success, or error message.
    """
    if not is_admin_logged_in():
        return jsonify(status='error', message='Not authorized'), 403
    filename = request.get_json().get('filename')
    if not filename:
        return jsonify(status='error', message='No filename provided')
    fpath = os.path.join(GALLERY_FOLDER, filename)
    if not os.path.isfile(fpath):
        return jsonify(status='error', message='File not found')
    try:
        os.remove(fpath)
        return jsonify(status='ok')
    except Exception as e:
        return jsonify(status='error', message=str(e))

# --- Supabase Setup ---
# SUPABASE_URL = os.getenv('SUPABASE_URL')
# SUPABASE_KEY = os.getenv('SUPABASE_KEY')
# supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# The following code was used to insert the initial admin user into Supabase.
# It is now commented out to avoid duplicate key errors.
'''
# Set your admin credentials
username = "admin"
password = "admin123"  # Change this to your desired password
email = "admin@example.com"

# Hash the password
password_hash = bcrypt.hash(password)

# Insert into Supabase
data = {
    "username": username,
    "password_hash": password_hash,
    "email": email
}
result = supabase.table("admins").insert(data).execute()
print(result)
'''

@app.route('/capture', methods=['POST'])
def capture():
    """
    Triggers the face matching process.
    Returns:
        JSON: {status: 'ok'} on success, or error message.
    """
    if os.path.exists(MATCHED_FOLDER):
        shutil.rmtree(MATCHED_FOLDER)
    os.makedirs(MATCHED_FOLDER, exist_ok=True)

    if os.path.exists(EMAIL_SENT_FLAG):
        os.remove(EMAIL_SENT_FLAG)

    try:
        subprocess.run(['python3', 'match_faces.py'], check=True)
    except subprocess.CalledProcessError:
        return jsonify(status='error', message="Face matching failed.")

    matched_files = [f for f in os.listdir(MATCHED_FOLDER) if f.startswith('clean_')]
    if not matched_files:
        return jsonify(status='no_face')

    # Trigger async post-matching process
    process_pending_request_async()

    return jsonify(status='ok')

@app.route('/admin/check_session')
def check_admin_session():
    """
    Checks if the admin is currently logged in.
    Returns:
        JSON: {"admin_logged_in": True/False}
    """
    return jsonify({"admin_logged_in": is_admin_logged_in()})

@app.route('/admin/change_password', methods=['POST'])
def admin_change_password():
    """
    Handles AJAX password change for admin portal.
    Expects JSON: {current_password, new_password}
    Returns: JSON status
    """
    if not is_admin_logged_in():
        return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    admin_username = session.get('admin_username')
    # Fetch admin from Supabase
    admin = None
    try:
        admin = supabase.table("admins").select("username,password_hash").eq("username", admin_username).single().execute().data
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Error fetching admin.'}), 500
    if not admin or not bcrypt.verify(current_password, admin["password_hash"]):
        return jsonify({'status': 'error', 'message': 'Current password is incorrect.'}), 400
    # Update password
    new_hash = bcrypt.hash(new_password)
    try:
        supabase.table("admins").update({"password_hash": new_hash}).eq("username", admin_username).execute()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Failed to change password.'}), 500

@app.route('/list_events')
def list_events():
    """
    Returns a JSON list of all event names (subfolders in static/gallery/).
    """
    try:
        event_names = [d for d in os.listdir(GALLERY_FOLDER)
                      if os.path.isdir(os.path.join(GALLERY_FOLDER, d)) and not d.startswith('.')]
        return jsonify(status='ok', events=event_names)
    except Exception as e:
        return jsonify(status='error', message=str(e))

if __name__ == '__main__':
    app.run(debug=True,port=5002)