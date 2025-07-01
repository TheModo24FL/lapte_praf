from flask import Flask, render_template, request, send_file, jsonify, redirect, flash
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
import json
import re
import traceback
import zipfile
import io
from datetime import datetime
import locale
from dbfread import DBF
import pandas as pd
import email.utils

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER')
TEMPLATES_FILE = os.getenv('TEMPLATES_FILE')
LAST_TEMPLATE_FILE = os.getenv('LAST_TEMPLATE_FILE')

def get_file_info(filepath):
    timestamp = os.path.getmtime(filepath)
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

def get_file_size(filepath):
    size_bytes = os.path.getsize(filepath)
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    else:
        return f"{size_bytes/(1024*1024):.1f} MB"

def get_files_recursive(directory):
    structure = {}
    # Define patterns for matching files
    lp_pattern = re.compile(r'LP\d{6}\.DBF$', re.IGNORECASE)
    cent_pattern = re.compile(r'CENT_MED\.TXT$', re.IGNORECASE)
    
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        rel_path = os.path.relpath(item_path, UPLOAD_FOLDER)
        
        if os.path.isfile(item_path):
            # Check if file matches either pattern
            if lp_pattern.match(item) or cent_pattern.match(item):
                parent = os.path.dirname(rel_path)
                file_info = {
                    'name': item,
                    'modified': get_file_info(item_path),
                    'size': get_file_size(item_path)
                }
                if parent == '':
                    if 'root' not in structure:
                        structure['root'] = []
                    structure['root'].append(file_info)
                else:
                    if parent not in structure:
                        structure[parent] = []
                    structure[parent].append(file_info)
        elif os.path.isdir(item_path):
            subfiles = get_files_recursive(item_path)
            if subfiles:  # Only add folders that contain matching files
                structure.update(subfiles)
    
    return structure

def load_templates():
    try:
        with open(TEMPLATES_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def add_template(recipient, subject, message, name):
    templates = load_templates()
    templates.append({
        'name': name,
        'recipient': recipient,
        'subject': subject,
        'message': message
    })
    with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(templates, f, indent=4, ensure_ascii=False, sort_keys=True)

def save_last_template(template_index):
    try:
        with open(LAST_TEMPLATE_FILE, 'w') as f:
            f.write(str(template_index))
    except:
        pass

def get_last_template():
    try:
        with open(LAST_TEMPLATE_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return -1

def get_default_subject():
    # Set locale to Romanian
    locale.setlocale(locale.LC_TIME, 'ro_RO.UTF-8')
    current_date = datetime.now()
    # Get month name in Romanian and capitalize first letter
    month = current_date.strftime('%B').lower().capitalize()
    year = current_date.strftime('%Y')
    subject_format = os.getenv('SUBJECT_FORMAT', 'Raportare lapte praf Tomesti {month} {year}')
    return subject_format.format(month=month, year=year)

@app.route('/')
def index():
    files = get_files_recursive(UPLOAD_FOLDER)
    templates = load_templates()
    last_template = get_last_template()
    default_subject = get_default_subject()
    return render_template('index.html', 
                         folders=files, 
                         templates=templates, 
                         last_template=last_template,
                         default_subject=default_subject)

@app.route('/settings')
def settings():
    templates = load_templates()
    smtp_settings = {
        'server': os.getenv('SMTP_SERVER'),
        'port': os.getenv('SMTP_PORT'),
        'username': os.getenv('SMTP_USERNAME'),
        'password': os.getenv('SMTP_PASSWORD'),
        'sender_email': os.getenv('SENDER_EMAIL'),
        'sender_name': os.getenv('SENDER_NAME', ''),
        'use_zip': os.getenv('USE_ZIP', 'false').lower(),
        'bcc_enabled': os.getenv('BCC_ENABLED', 'false').lower(),
        'subject_format': os.getenv('SUBJECT_FORMAT', 'Raportare lapte praf Tomesti {month} {year}')
    }
    default_subject = get_default_subject()
    return render_template('settings.html', templates=templates, smtp=smtp_settings, default_subject=default_subject)

@app.route('/delete_template/<int:index>', methods=['POST'])
def delete_template(index):
    templates = load_templates()
    if 0 <= index < len(templates):
        templates.pop(index)
        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates, f, indent=4, ensure_ascii=False, sort_keys=True)
    return jsonify({'status': 'success'})

@app.route('/update_template', methods=['POST'])
def update_template():
    try:
        index = int(request.form['index'])
        templates = load_templates()
        if 0 <= index < len(templates):
            templates[index].update({
                'name': request.form['name'],
                'recipient': request.form['recipient'],
                'subject': request.form['subject'],
                'message': request.form['message']
            })
            with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
                json.dump(templates, f, indent=4, ensure_ascii=False, sort_keys=True)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/update_smtp', methods=['POST'])
def update_smtp():
    try:
        use_zip = 'true' if request.form.get('use_zip') == 'on' else 'false'
        bcc_enabled = 'true' if request.form.get('bcc_enabled') == 'on' else 'false'
        env_content = f"""SMTP_SERVER={request.form['server']}
SMTP_PORT={request.form['port']}
SMTP_USERNAME={request.form['username']}
SMTP_PASSWORD={request.form['password']}
SENDER_EMAIL={request.form['sender_email']}
SENDER_NAME={request.form['sender_name']}
USE_ZIP={use_zip}
BCC_ENABLED={bcc_enabled}
SUBJECT_FORMAT={request.form['subject_format']}
APP_ROOT={os.getenv('APP_ROOT')}
UPLOAD_FOLDER={os.getenv('UPLOAD_FOLDER')}
TEMPLATES_FILE={os.getenv('TEMPLATES_FILE')}
LAST_TEMPLATE_FILE={os.getenv('LAST_TEMPLATE_FILE')}"""
        
        env_path = os.path.join(os.getenv('APP_ROOT', '/'), '.env')
        with open(env_path, 'w') as f:
            f.write(env_content)
        load_dotenv(override=True)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/send_email', methods=['POST'])
def send_email():
    server = None
    try:
        selected_files = request.form.getlist('files')
        recipient = request.form['recipient']
        subject = request.form['subject']
        message = request.form['message']
        save_template = request.form.get('save_template') == 'on'
        template_name = request.form.get('template_name', '')
        template_index = request.form.get('template_index', '')
        
        if template_index:
            save_last_template(template_index)
        
        # Debug log
        print(f"Sending email to: {recipient}")
        print(f"SMTP Settings: {os.getenv('SMTP_SERVER')}:{os.getenv('SMTP_PORT')}")
        print(f"Selected files: {selected_files}")
        
        msg = MIMEMultipart('mixed')
        sender_name = os.getenv('SENDER_NAME')
        sender_email = os.getenv('SENDER_EMAIL')
        
        # Set proper From header with required email address but display only name
        msg['From'] = email.utils.formataddr((sender_name, sender_email))
        msg['To'] = recipient
        msg['Subject'] = subject

        # Add Reply-To header
        msg['Reply-To'] = sender_email
        
        # Add BCC if enabled
        if os.getenv('BCC_ENABLED', 'false').lower() == 'true':
            msg['Bcc'] = sender_email
        
        # Add both plain text and HTML versions        
        msg.attach(MIMEText(message, 'html'))
        
        # Group files by folder
        files_by_folder = {}
        for filename in selected_files:
            folder = os.path.dirname(filename) or 'root'
            if folder not in files_by_folder:
                files_by_folder[folder] = []
            files_by_folder[folder].append(filename)
        
        use_zip = os.getenv('USE_ZIP', 'false').lower() == 'true'
        
        if use_zip:
            # Create and attach archives for each folder
            for folder, files in files_by_folder.items():
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filename in files:
                        filepath = os.path.join(UPLOAD_FOLDER, filename)
                        # Keep original folder structure in ZIP
                        zip_file.write(filepath, filename)
                
                zip_buffer.seek(0)
                attachment = MIMEApplication(zip_buffer.read())
                zip_name = f"{os.path.basename(folder)}.zip" if folder != 'root' else "root.zip"
                attachment.add_header('Content-Disposition', 'attachment', filename=zip_name)
                msg.attach(attachment)
        else:
            # Attach files individually with original paths
            for filename in selected_files:
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, 'rb') as f:
                    attachment = MIMEApplication(f.read())
                    # Use original filename
                    attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filename))
                    msg.attach(attachment)
        
        try:
            print("Connecting to SMTP server...")
            smtp_server = os.getenv('SMTP_SERVER')
            smtp_port = int(os.getenv('SMTP_PORT'))
            username = os.getenv('SMTP_USERNAME')
            password = os.getenv('SMTP_PASSWORD')

            # Use a context manager for SMTP connection
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()  # Say hello to the server
                print("Connected to SMTP server")
                
                print("Attempting login...")
                server.login(username, password)
                print("Login successful")
                
                print("Sending message...")
                server.send_message(msg)
                print("Message sent")
            
            if save_template and template_name:
                add_template(recipient, subject, message, template_name)
                save_last_template(len(load_templates()) - 1)
            
            flash('Email sent successfully!', 'success')
            return redirect('/')
            
        except smtplib.SMTPAuthenticationError:
            error_msg = "SMTP Authentication failed. Please check your username and password."
            print(error_msg)
            flash(error_msg, 'error')
            return redirect('/')
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error occurred: {str(e)}"
            print(error_msg)
            flash(error_msg, 'error')
            return redirect('/')
            
    except Exception as e:
        print("Unexpected error:", traceback.format_exc())
        flash('An unexpected error occurred', 'error')
        return redirect('/')
    finally:
        if server and not isinstance(server, smtplib.SMTP_SSL):
            try:
                server.quit()
            except:
                pass

@app.route('/preview_file/<path:filename>')
def preview_file(filename):
    try:
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if filename.lower().endswith('.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'status': 'success', 'content': content, 'type': 'text'})
        elif filename.lower().endswith('.dbf'):
            # Read DBF file
            table = DBF(filepath, encoding='cp852')  # using cp852 for Romanian characters
            # Convert to pandas DataFrame for easier handling
            df = pd.DataFrame(list(table))
            # Convert DataFrame to HTML table with Bootstrap classes
            html_table = df.to_html(classes=['table', 'table-striped', 'table-bordered', 'table-sm'])
            return jsonify({'status': 'success', 'content': html_table, 'type': 'dbf'})
        else:
            return jsonify({'status': 'error', 'message': 'Only .txt and .dbf files can be previewed'}), 400
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=True)
