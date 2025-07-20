import requests
import os
from dotenv import load_dotenv
load_dotenv()

def add_discord_role(user, role):
    """
    Adds the discord role for a user
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    user_id = user.discord_id
    token = os.getenv("DISCORD_BOT_API_TOKEN")

    url = os.getenv("DISCORD_BOT_API") + f"/{user_id}/roles/add"
    json = {
        "roles": [role],
        "token": token
    }
    requests.post(url, json=json)

def add_discord_roles(user, roles):
    """
    Adds the discord roles for a user
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    user_id = user.discord_id
    token = os.getenv("DISCORD_BOT_API_TOKEN")

    url = os.getenv("DISCORD_BOT_API") + f"/{user_id}/roles/add"
    json = {
        "roles": roles,
        "token": token
    }
    requests.post(url, json=json)

def remove_discord_role(user, role):
    """
    Removes the discord role for a user
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    user_id = user.discord_id
    token = os.getenv("DISCORD_BOT_API_TOKEN")

    url = os.getenv("DISCORD_BOT_API") + f"/{user_id}/roles/remove"
    json = {
        "roles": [role],
        "token": token
    }
    requests.post(url, json=json)

def remove_discord_roles(user, roles):
    """
    Removes the discord roles for a user
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    if user is None or not user.is_active:
        return "Could not find User", 404
    
    user_id = user.discord_id
    token = os.getenv("DISCORD_BOT_API_TOKEN")

    url = os.getenv("DISCORD_BOT_API") + f"/{user_id}/roles/remove"
    json = {
        "roles": roles,
        "token": token
    }
    requests.post(url, json=json)
    