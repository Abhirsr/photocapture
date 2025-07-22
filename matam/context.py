"""
Shared context for Supabase client and Flask-Mail setup.
"""
import os  # For environment variable access
from supabase import create_client, Client  # Supabase client for database and storage
from flask_mail import Mail, Message  # Flask-Mail for email sending
from dotenv import load_dotenv  # For loading .env configuration

load_dotenv()  # Load environment variables from .env file

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)  # Supabase client instance

mail = Mail()  # Flask-Mail instance for sending emails 