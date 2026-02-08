"""
HR AI Assistant - OpenAI Integration
This handles the AI conversation logic using Azure OpenAI
"""

import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class HRAssistant:
    """
    HR AI Assistant that answers candidate questions
    """
    
    def __init__(self):
        """Initialize the Azure OpenAI client"""
        self.client = AzureOpenAI(
            api_key=os.getenv('AZURE_OPENAI_API_KEY'),
            api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
        )
        self.deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')
        
        # System prompt that defines the AI's behavior
        self.system_prompt = """
You are a professional HR interviewer conducting a phone interview.

Interview flow:
1. Start by greeting the candidate.
2. Ask the candidate which role they are interviewing for.
3. Once the role is known, ask 8–10 interview questions relevant to that role.
4. Ask one question at a time and wait for the answer before continuing.
5. Keep each question short and clear for a phone call.

Guidelines:
- Be polite, calm, and professional.
- Keep responses under 2 sentences.
- Do not explain your reasoning.
- If the role is unclear, ask a follow-up question.
- End the interview by thanking the candidate.

Speak naturally like a human interviewer.
"""
    def get_response(self, candidate_message):
        """
        Get AI response for candidate's question
        
        Args:
            candidate_message: The candidate's question or message
            
        Returns:
            AI's response as text
        """
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": candidate_message}
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error getting AI response: {str(e)}")
            return "I apologize, I'm having trouble processing that. Could you please repeat your question?"

# Test the assistant
if __name__ == "__main__":
    print("Testing HR AI Assistant...\n")
    
    assistant = HRAssistant()
    
    # Test questions
    test_questions = [
        "What is the interview process?",
        "What benefits do you offer?",
        "Is this a remote position?"
    ]
    
    for question in test_questions:
        print(f"Candidate: {question}")
        response = assistant.get_response(question)
        print(f"AI HR: {response}\n")
