import requests
import os
from dotenv import load_dotenv
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

load_dotenv()

def send_discord_dm(user_id: str, message: str) -> bool:
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False

    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + f"/dm"

    try:
        response = requests.post(url, json={"user_id": user_id, "message": message, "token": token})
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Discord DM: {str(e)}")
        return False


def set_discord_nickname(user_id: str, nickname: str) -> bool:
    """
    Sets the nickname of a user in the Discord server
    
    Args:
        user_id: The ID of the user to set the nickname for
        nickname: The new nickname to set for the user
        
    Returns:
        True if the nickname was set successfully, False otherwise
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False

    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + f"/{user_id}/set-nickname"
    
    json_data = {
        "user_id": user_id,
        "nickname": nickname,
        "token": token
    }
    
    try:
        response = requests.post(url, json=json_data)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to set Discord nickname: {str(e)}")
        return False

def create_discord_role(role_name: str, color: str = None) -> Optional[str]:
    """
    Creates a new role in the Discord server
    
    Args:
        role_name: The name of the role to create
        color: The color of the role as a hex string (e.g., "FF0000" for red)
        
    Returns:
        The ID of the created role on success, None on failure
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + "/roles/create"
    
    json_data = {
        "role_name": role_name,
        "token": token
    }
    
    if color:
        json_data["color"] = color
    
    try:
        response = requests.post(url, json=json_data)
        response.raise_for_status()  # Raise an exception for non-2xx status codes
        role_data = response.json()
        return role_data.get("role_id")  # Return the role ID
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to create Discord role: {str(e)}")
        return None

def create_discord_text_channel(
    channel_name: str,
    category: str = "Events",
    role_name_list: List[str] = None,
    user_id_list: List[int] = None
) -> Optional[str]:
    """
    Creates a new text channel in the Discord server with specific permissions
    
    Args:
        channel_name: The name of the text channel to create
        category_id: The category ID to place the channel under
        role_id_list: List of role IDs that can view and access the channel
        user_id_list: Optional list of user IDs that can view and access the channel
        
    Returns:
        The ID of the created channel on success, None on failure
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + "/channels/create-text"
    
    json_data = {
        "category_name": category,
        "channel_name": channel_name,
        "view_roles": role_name_list,  # Only team role can view
        "access_roles": role_name_list,  # Only team role can access
        "view_users": user_id_list if user_id_list else [],  # Optional: users who can view
        "access_users": user_id_list if user_id_list else [],  # Optional: users who can access
        "token": token
    }
    
    try:
        response = requests.post(url, json=json_data)
        response.raise_for_status()
        channel_data = response.json()
        return channel_data.get("channel_id")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to create Discord text channel: {str(e)}")
        return None

def create_discord_voice_channel(
    channel_name: str, 
    team_role_id: str
) -> Optional[str]:
    """
    Creates a new voice channel in the Discord server with specific permissions
    
    Args:
        channel_name: The name of the voice channel to create
        category_id: The category ID to place the channel under
        team_role_id: The role ID that can connect to this channel
        
    Returns:
        The ID of the created channel on success, None on failure
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + "/channels/create-voice"
    
    # Get category name from category ID (assuming we already have it)
    category_name = "Events"  # Default to "events" if we can't determine it
    
    json_data = {
        "category_name": category_name,
        "channel_name": channel_name,
        "view_roles": [],  # Everyone can view
        "access_roles": [team_role_id],  # Only team role can connect
        "token": token
    }
    
    try:
        response = requests.post(url, json=json_data)
        response.raise_for_status()
        channel_data = response.json()
        return channel_data.get("channel_id")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to create Discord voice channel: {str(e)}")
        return None

def get_event_category_id() -> Optional[str]:
    """
    Gets the ID of the "events" category in the Discord server
    
    Returns:
        The ID of the events category if found, None otherwise
    """
    if os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") != "production":
        return False
    
    token = os.getenv("DISCORD_BOT_API_TOKEN")
    url = os.getenv("DISCORD_BOT_API") + "/channels/list"
    
    try:
        response = requests.get(url, params={"token": token})
        response.raise_for_status()
        channels = response.json()
        
        # Look for a category channel named "events" (case insensitive)
        for channel in channels:
            if channel.get("type") == 4 and channel.get("name", "").lower() == "events":  # 4 = category
                return channel.get("id")
                
        # If no category named "events" was found, return None
        logging.warning("No 'events' category found in Discord server")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get Discord categories: {str(e)}")
        return None


def discord_sync_enabled() -> bool:
    """Bot calls only happen in production; elsewhere every helper is a no-op."""
    return os.getenv("RAILWAY_ENVIRONMENT_NAME", "local") == "production"


def list_discord_channels() -> Optional[List[Dict[str, Any]]]:
    """Stage, voice and text channels a Discord event can be held in or point to,
    in display order. None when the bot can't be asked."""
    if not discord_sync_enabled():
        return None

    url = os.getenv("DISCORD_BOT_API") + "/channels"
    try:
        response = requests.get(url, params={"token": os.getenv("DISCORD_BOT_API_TOKEN")}, timeout=10)
        response.raise_for_status()
        return response.json().get("channels")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to list Discord channels: {str(e)}")
        return None


def _scheduled_event_body(name: str, start: datetime, end: datetime, channel_id: Optional[str],
                          location: Optional[str], image_url: Optional[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "channel_id": channel_id,
        "location": location,
        "image_url": image_url,
        "token": os.getenv("DISCORD_BOT_API_TOKEN"),
    }


def create_discord_scheduled_event(name: str, start: datetime, end: datetime, channel_id: Optional[str] = None,
                                   location: Optional[str] = None, image_url: Optional[str] = None) -> Optional[str]:
    """Creates a Discord scheduled event in a stage/voice channel, or an external
    one at `location`. Returns its id, or None on failure."""
    if not discord_sync_enabled():
        return None

    url = os.getenv("DISCORD_BOT_API") + "/scheduled-events"
    body = _scheduled_event_body(name, start, end, channel_id, location, image_url)
    try:
        response = requests.post(url, json=body, timeout=30)
        response.raise_for_status()
        return response.json().get("id")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to create Discord scheduled event: {str(e)}")
        return None


def update_discord_scheduled_event(event_id: str, name: str, start: datetime, end: datetime,
                                   channel_id: Optional[str] = None, location: Optional[str] = None,
                                   image_url: Optional[str] = None) -> str:
    """Updates a Discord scheduled event. A None image_url removes its cover.

    Returns "ok", "missing" (the event no longer exists in Discord, e.g. it was
    deleted by hand, so the caller should recreate it), or "failed".
    """
    if not discord_sync_enabled():
        return "failed"

    url = os.getenv("DISCORD_BOT_API") + f"/scheduled-events/{event_id}"
    body = _scheduled_event_body(name, start, end, channel_id, location, image_url)
    try:
        # Longer than the other calls: the bot downloads the cover photo first.
        response = requests.patch(url, json=body, timeout=30)
        if response.status_code == 404:
            return "missing"
        response.raise_for_status()
        return "ok"
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to update Discord scheduled event {event_id}: {str(e)}")
        return "failed"


def delete_discord_scheduled_event(event_id: str) -> bool:
    """Deletes a Discord scheduled event. An already-deleted event counts as success (bot side)."""
    if not discord_sync_enabled():
        return False

    url = os.getenv("DISCORD_BOT_API") + f"/scheduled-events/{event_id}"
    try:
        response = requests.delete(url, json={"token": os.getenv("DISCORD_BOT_API_TOKEN")}, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to delete Discord scheduled event {event_id}: {str(e)}")
        return False
