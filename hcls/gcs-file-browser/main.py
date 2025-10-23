import datetime
import google.oauth2.credentials
import json
import logging
import os
from datetime import timedelta
from flask import Flask, request, render_template, redirect, url_for, Response, flash
from google.auth import default
from google.cloud import storage
from pathlib import Path
from werkzeug.utils import secure_filename



# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.urandom(24) # Needed for flash messages

# --- Configuration ---
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
TOKEN = os.environ.get('TOKEN')
if not GCS_BUCKET_NAME:
    logging.error("GCS_BUCKET_NAME environment variable not set.")
    # Consider raising an error or exiting for local dev if not set

credentials, project_id = default()
storage_client = storage.Client(project_id)

def get_bucket():
    if not GCS_BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not configured.")
    try:
        return storage_client.get_bucket(GCS_BUCKET_NAME)
    except Exception as e:
        logging.error(f"Failed to get bucket {GCS_BUCKET_NAME}: {e}")
        return None

def generate_breadcrumbs(path_str):
    """Generates breadcrumb parts for navigation."""
    parts = []
    if not path_str:
        return parts
    
    elements = path_str.strip('/').split('/')
    current_path = ''
    for i, element in enumerate(elements):
        if i > 0:
            current_path += '/'
        current_path += element
        parts.append({'name': element, 'path': current_path + ('/' if i < len(elements) -1 else '')})
    return parts


# Route for browsing, handles root and subpaths
@app.route('/', defaults={'path': ''})
@app.route('/browse/', defaults={'path': ''}) # Explicit browse route
@app.route('/browse/<path:path>')
def browse_path(path):
    """Lists folders and JSON files at a given GCS path (prefix)."""
    bucket = get_bucket()
    if not bucket:
        flash("GCS Bucket not configured or accessible.", "error")
        return render_template('browser.html', current_path_display=path, current_path_for_upload=path, folders=[], files=[], parent_path=None, breadcrumb_parts=[])

    # Normalize path to always end with a '/' if not empty, for prefix matching
    current_prefix = path.strip('/')
    if current_prefix:
        current_prefix += '/'
    
    current_path_for_upload = current_prefix # Used for uploads, has trailing slash
    current_path_display = path.strip('/') # Used for display, no trailing slash for root

    folders = []
    files_list = []
    parent_path = None

    try:
        # list_blobs with delimiter simulates folders
        blobs_iterator = bucket.list_blobs(prefix=current_prefix, delimiter='/')
        
        # Files in the current directory
        for blob in blobs_iterator: # These are the actual blobs (files)
            #if blob.name.lower().endswith('.json') and blob.name != current_prefix: # Exclude the "folder" object itself if it exists
            if blob.name.lower().endswith(('.json', '.cif')) and blob.name != current_prefix: # Exclude the "folder" object itself if it exists
                 # Store as object to keep both name (full path) and size if needed later
                files_list.append({'name': blob.name, 'size': blob.size})

        # Subdirectories (prefixes)
        if hasattr(blobs_iterator, 'prefixes') and blobs_iterator.prefixes:
            for p in blobs_iterator.prefixes:
                folders.append(p) # p already includes the trailing slash

        # Determine parent path for "Go Up"
        if current_prefix: # If not at root
            if '/' in current_prefix.strip('/'):
                parent_path = '/'.join(current_prefix.strip('/').split('/')[:-1])
                if parent_path: # Ensure parent_path also has trailing slash if not root
                    parent_path += '/'
            else: # We are in a top-level folder, parent is root
                parent_path = '' # Root path
        
    except Exception as e:
        logging.error(f"Error listing contents for prefix '{current_prefix}': {e}")
        flash(f"Error listing contents: {e}", "error")

    retrieved_filename = request.args.get('retrieved_filename')
    retrieved_content = request.args.get('retrieved_content')
    success_message = request.args.get('success_message')
    error_message = request.args.get('error_message')

    message = success_message or error_message
    success = bool(success_message)

    breadcrumb_parts = generate_breadcrumbs(current_path_display)
    blob = bucket.blob(current_path_display)
    # Now, to get the gsutil-style path:
    gsutil_path = f"gs://{bucket.name}/{blob.name}"

    return render_template('browser.html',
                           folders=sorted(folders),
                           files=sorted(files_list, key=lambda x: x['name']),
                           gsutil_path = gsutil_path,
                           current_path_display=current_path_display,
                           current_path_for_upload=current_path_for_upload,
                           parent_path=parent_path,
                           message=message,
                           success=success,
                           retrieved_filename=retrieved_filename,
                           retrieved_content=retrieved_content,
                           breadcrumb_parts=breadcrumb_parts)

FIXED_UPLOAD_DIRECTORY = "data_pipeline_toprocess/"

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        # Redirect to a relevant path, perhaps the root or a specific browse path
        return redirect(url_for('browse_path', path=''))

    file = request.files['file']

    if file.filename == '':
        flash('No file selected for uploading.', 'error')
        return redirect(url_for('browse_path', path=''))

    if file and file.filename.lower().endswith('.json'):
        filename = secure_filename(file.filename)
        
        # Use the fixed directory for the blob name
        blob_name = os.path.join(FIXED_UPLOAD_DIRECTORY, filename).replace("\\", "/")

        try:
            try:
                # Validate JSON content before uploading
                json.load(file)
                # Reset file pointer to the beginning for upload
                file.seek(0)
            except json.JSONDecodeError:
                flash(f"Invalid JSON content in {filename}.", 'error')
                return redirect(url_for('browse_path', path=''))

            bucket = get_bucket()
            if not bucket:
                flash("GCS Bucket not configured or accessible.", "error")
                return redirect(url_for('browse_path', path=''))

            blob = bucket.blob(blob_name)
            blob.upload_from_file(file, content_type='application/json')
            
            logging.info(f"File {blob_name} uploaded to {GCS_BUCKET_NAME}.")
            flash(f"File {filename} uploaded to '{FIXED_UPLOAD_DIRECTORY}' successfully!", 'success')
            
            # Redirect to a relevant path after upload
            return redirect(url_for('browse_path', path=''))

        except Exception as e:
            logging.error(f"Failed to upload {blob_name}: {e}")
            flash(f"Failed to upload {filename}: {e}", 'error')
            return redirect(url_for('browse_path', path=''))
    else:
        flash('Invalid file type. Only .json files are allowed.', 'error')
        return redirect(url_for('browse_path', path=''))


def access_secret_version(project_id, secret_id, version_id="latest"):
    """
    Accesses the payload for the given secret version.
    The version can be a version number (e.g., "1", "2") or "latest".
    """
    try:
        # Create the Secret Manager client.
        client = secretmanager.SecretManagerServiceClient()

        # Build the resource name of the secret version.
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

        # Access the secret version.
        response = client.access_secret_version(request={"name": name})

        # Decode the payload.
        payload = response.payload.data.decode("UTF-8")
        return payload.replace('\n', '')  

    except Exception as e:
        print(f"Error accessing secret '{secret_id}' version '{version_id}': {e}")
        return None


@app.route('/retrieve_page', methods=['GET']) # Renamed for clarity
def retrieve_file_page():
    full_path = request.args.get('full_path') # Now expects full object path
    current_view_path = request.args.get('current_view_path', '') # To return to the correct folder view

    if not full_path:
        flash("Filename (full path) not provided for retrieval.", "error")
        return redirect(url_for('browse_path', path=current_view_path))

    # full_path is already the GCS object name, no need to secure_filename on it here
    # as it's derived from GCS listing.

    try:
        bucket = get_bucket()
        if not bucket:
            flash("GCS Bucket not configured or accessible.", "error")
            return redirect(url_for('browse_path', path=current_view_path))

        blob = bucket.blob(full_path)
        if blob.exists():
            content = blob.download_as_text()
            try:
                parsed_json = json.loads(content)
                pretty_content = json.dumps(parsed_json, indent=2)
            except json.JSONDecodeError:
                pretty_content = content
            
            logging.info(f"File {full_path} retrieved for display.")
            # Pass content back to browse_path for rendering
            return redirect(url_for('browse_path', path=current_view_path, retrieved_filename=full_path, retrieved_content=pretty_content))
        else:
            flash(f"File {full_path} not found.", 'error')
            return redirect(url_for('browse_path', path=current_view_path))

    except Exception as e:
        logging.error(f"Failed to retrieve {full_path} for display: {e}")
        flash(f"Failed to retrieve {full_path}: {e}", 'error')
        return redirect(url_for('browse_path', path=current_view_path))


@app.route('/retrieve_raw/<path:full_path>', methods=['GET']) # Use path converter
def retrieve_file_get(full_path):
    """Serves the raw JSON file content, given its full GCS object path."""
    # full_path is directly from URL, assuming it's already correct from GCS listing.
    # No need for secure_filename here as it would strip slashes.
    # Be cautious if this path could be user-manipulated in other ways.

    if not full_path.lower().endswith(('.json', '.cif')):
        return Response("Invalid filename or not a JSON file.", status=400, mimetype='text/plain')

    try:
        bucket = get_bucket()
        if not bucket:
             return Response("GCS Bucket not configured or accessible.", status=500, mimetype='text/plain')
        blob = bucket.blob(full_path) # Use the full path

        if blob.exists():
            content = blob.download_as_text()
            logging.info(f"Serving raw file {full_path}.")
            return Response(content, mimetype='application/json')
        else:
            return Response(f"File {full_path} not found.", status=404, mimetype='text/plain')
    except Exception as e:
        logging.error(f"Failed to serve raw file {full_path}: {e}")
        return Response(f"Error retrieving file: {e}", status=500, mimetype='text/plain')


@app.route('/retrieve_signed_url/<path:full_path>', methods=['GET']) # Use path converter
def retrieve_signed_url(full_path):
    """Serves the raw JSON file content, given its full GCS object path."""
    # full_path is directly from URL, assuming it's already correct from GCS listing.
    # No need for secure_filename here as it would strip slashes.
    # Be cautious if this path could be user-manipulated in other ways.

    if not full_path.lower().endswith(('.json', '.cif')):
        return Response("Invalid filename or not a JSON file.", status=400, mimetype='text/plain')

    try:
        bucket = get_bucket()
        if not bucket:
             return Response("GCS Bucket not configured or accessible.", status=500, mimetype='text/plain')
        blob = bucket.blob(full_path) # Use the full path

        if blob.exists():
            signed_url = generate_download_url(bucket, blob)
            logging.info(f"Serving url file {signed_url}.")
            file_only_pathlib = Path(blob.name).name
            download_command = f"!wget -O {file_only_pathlib} '{signed_url}'"
            return Response(download_command, mimetype='text/plain')
        else:
            return Response(f"File {full_path} not found.", status=404, mimetype='text/plain')
    except Exception as e:
        logging.error(f"Failed to serve raw file {full_path}: {e}")
        return Response(f"Error retrieving file: {e}", status=500, mimetype='text/plain')



def generate_download_url(bucket, blob):
    """Generates a v4 signed URL for downloading a blob.

    Note: This method requires the service account to have the
    'Service Account Token Creator' IAM role.
    """
    
    # Initialize the client

    # Set the expiration time for the URL
    # In this example, the URL will be valid for 1 hour
    expiration_time = datetime.timedelta(hours=1)

    try:
        # Generate the signed URL
        signed_url = blob.generate_signed_url(
            version="v4",  # Recommended version
            expiration=expiration_time,
            method="GET",  # Allow the user to GET (download) the file
        )
        
        return signed_url

    except Exception as e:
        print(f"Error generating signed URL: {e}")
        return None


if __name__ == '__main__':
    if not GCS_BUCKET_NAME:
        print("Error: GCS_BUCKET_NAME environment variable is not set.")
    else:
        app.run(host='127.0.0.1', port=8080, debug=True)