"""
Shared admin state management
"""

# Global dictionary to store admin conversation states
admin_conversations = {}

def get_admin_conversations():
    """Get the admin conversations dictionary"""
    return admin_conversations

def clear_admin_conversation(user_id: int):
    """Clear admin conversation for a user"""
    if user_id in admin_conversations:
        del admin_conversations[user_id]
        return True
    return False

def has_admin_conversation(user_id: int) -> bool:
    """Check if user has active admin conversation"""
    return user_id in admin_conversations

def set_admin_conversation(user_id: int, conversation_data: dict):
    """Set admin conversation for a user"""
    admin_conversations[user_id] = conversation_data

print("✅ Admin state management loaded")
