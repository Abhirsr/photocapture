"""
Background task for zipping matched images, uploading to Supabase, and emailing results to the user.
"""
import os
import zipfile
import tempfile
import multiprocessing
multiprocessing.set_start_method('forkserver', force=True)
from context import supabase, mail, Message

def process_user_request(request_id):
    """
    Processes a user request to zip matched images, upload to Supabase, and send email.
    Args:
        request_id (str): The unique ID of the user request.
    """
    # Fetch the user request row from Supabase
    row = supabase.table('user_requests').select('*').eq('id', request_id).single().execute().data
    if not row:
        supabase.table('user_requests').update({'status': 'error', 'error_message': 'Request not found.'}).eq('id', request_id).execute()
        print(f"[ERROR] Request {request_id} not found.")
        return
    recipient = row['email']
    selected_images = row.get('matched_files', [])
    # If no email or no images, mark as error
    if not recipient:
        supabase.table('user_requests').update({'status': 'error', 'error_message': 'No email provided.'}).eq('id', request_id).execute()
        print(f"[ERROR] Request {request_id}: No email provided.")
        return
    if not selected_images:
        supabase.table('user_requests').update({'status': 'error', 'error_message': 'No matched images found.'}).eq('id', request_id).execute()
        print(f"[ERROR] Request {request_id}: No matched images found.")
        return
    MATCHED_FOLDER = 'static/matched'
    image_paths = [os.path.join(MATCHED_FOLDER, f) for f in selected_images]
    try:
        # Create a zip file of the matched images
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip, 'w') as zipf:
                for idx, file_path in enumerate(image_paths, 1):
                    ext = os.path.splitext(file_path)[1]
                    new_name = f"matched_{idx}{ext}"
                    zipf.write(file_path, new_name)
            zip_path = tmp_zip.name
        # Upload the zip to Supabase Storage
        bucket_name = "matched-results"
        zip_filename = f"matched_{recipient.replace('@', '_').replace('.', '_')}_{request_id}.zip"
        with open(zip_path, "rb") as f:
            upload_response = supabase.storage.from_(bucket_name).upload(
                zip_filename, f, {"content-type": "application/zip", "x-upsert": "true"}
            )
        # Get the public URL for the uploaded zip
        public_url = supabase.storage.from_(bucket_name).get_public_url(zip_filename)
        # Send the email with the download link
        msg = Message("Face Match Results", recipients=[recipient])
        msg.body = f"\U0001F4C1 Your matched images are here:\n\n{public_url}"
        mail.send(msg)
        # Update the user request row with the zip URL and status
        supabase.table('user_requests').update({
            'zip_url': public_url,
            'status': 'done',
            'error_message': ''
        }).eq('id', request_id).execute()
        # Clean up the temporary zip file
        os.remove(zip_path)
    except Exception as e:
        # On error, mark the request as error and log the reason
        supabase.table('user_requests').update({'status': 'error', 'error_message': str(e)}).eq('id', request_id).execute()
        print(f"[ERROR] Request {request_id}: Exception occurred: {e}") 