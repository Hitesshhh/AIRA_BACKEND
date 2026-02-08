"""
HR AI Assistant - Main Entry Point
This script initiates a phone call to a candidate using Twilio
"""

import os
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables from .env file
load_dotenv()

def make_call(phone_number):
    """
    Makes a phone call to the given number using Twilio
    
    Args:
        phone_number: The phone number to call (format: +1234567890)
    """
    # Get Twilio credentials from environment variables
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
    server_url = os.getenv('SERVER_URL')
    applicationsid = os.getenv('TWILIO_APPLICATION_SID')
    
    # Check if all required credentials are present
    if not all([account_sid, auth_token, twilio_number, server_url]):
        print("ERROR: Missing Twilio credentials in .env file!")
        return
    
    # Create Twilio client
    client = Client(account_sid, auth_token)
    
    try:
        # Make the call
        print(f"\n🤖 HR AI Assistant is calling {phone_number}...")
        print("Please wait...\n")
        
        call = client.calls.create(
            to=phone_number,
            from_=twilio_number,
            url=f"{server_url}/voice",  # This URL handles the call
            status_callback=f"{server_url}/call-status",
            status_callback_event=['completed'],
            # application_sid = applicationsid
        )
        
        print(f"✅ Call initiated successfully!")
        print(f"Call SID: {call.sid}")
        print(f"Status: {call.status}")
        print("\nThe AI HR Assistant will now talk to the candidate.")
        print("Call will end when the candidate hangs up.\n")
        
    except Exception as e:
        print(f"❌ Error making call: {str(e)}")

if __name__ == "__main__":
    print("=" * 50)
    print("   HR AI ASSISTANT - PHONE CALL SYSTEM")
    print("=" * 50)
    print("\nMake sure your Flask server is running!")
    print("Run: python server.py\n")
    
    # Get phone number from user
    phone_number = input("Enter candidate's phone number (with country code, e.g., +1234567890): ")
    
    # Validate basic format
    if not phone_number.startswith('+'):
        print("⚠️  Phone number should start with + and country code")
        phone_number = '+' + phone_number
    
    # Make the call
    make_call(phone_number)
