"""
Item system for Stability Party 3

This module handles all item-related functionality including:
- Item creation and registration
- Item activation and effects
- Random shop item generation
- Team inventory management
"""

import random
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from models.models import EventTeams
from event_handlers.stability_party.save_data import SaveData, save_team_data
from event_handlers.stability_party.item_definitions import (
    ITEM_HANDLERS, get_item, get_all_items
)
from event_handlers.stability_party.send_event_notification import send_event_notification

# Item rarity weights for random selection
RARITY_WEIGHTS = {
    "common": 50,
    "uncommon": 30, 
    "rare": 15,
    "epic": 4,
    "legendary": 1
}

def get_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    """
    Get an item by ID - tries the code registry first, falls back to database
    
    Args:
        item_id: The item identifier
        
    Returns:
        Item data or None if not found
    """
    try:
        # First try to get from registry (items defined in code)
        registry_item = get_item(item_id)
        if registry_item:
            return registry_item.to_dict()
            
        return None
    except Exception as e:
        logging.error(f"Error fetching item {item_id}: {str(e)}")
        return None

def get_team_items(team_id: str, event_id: str) -> List[Dict[str, Any]]:
    """Get all items owned by a team"""
    try:
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            logging.error(f"Team not found: {team_id}")
            return []
        
        save = SaveData.from_dict(team.data)
        item_details = []
        
        for item_entry in save.itemList:
            item_id = item_entry.get("id")
            item = get_item_by_id(item_id)
            if item:
                # Merge the base item data with any instance-specific data
                item_data = {
                    "id": item_id,
                    "name": item["name"],
                    "description": item["description"],
                    "image": item["image"],
                    "item_type": item["item_type"],
                    "rarity": item["rarity"],
                    "uses_remaining": item_entry.get("uses_remaining", item["uses"]),
                    "purchased_at": item_entry.get("purchased_at"),
                    "activation_type": item["activation_type"],
                    "can_be_activated": item["activation_type"] == "active" and item_entry.get("uses_remaining", item["uses"]) > 0
                }
                item_details.append(item_data)
        
        return item_details
    except Exception as e:
        logging.error(f"Error getting team items: {str(e)}")
        return []

def generate_shop_inventory(event_id: str, shop_tier: int = 1, item_count: int = 3) -> List[Dict[str, Any]]:
    """
    Generate a random selection of items for a shop based on shop tier.
    
    Parameters:
    - event_id: The event these items belong to
    - shop_tier: The tier/level of the shop (higher tiers have better items)
    - item_count: Number of items to generate
    
    Returns:
    - List of item dictionaries for the shop
    """
    try:
        # Get all available items from registry
        all_items = [item.to_dict() for item in get_all_items()]
        
        if not all_items:
            logging.warning(f"No items found for shop generation")
            return []
        
        # Prepare empty result list
        shop_items = []
        
        # Keep track of selected items to avoid duplicates
        selected_item_ids = set()
        
        # Adjust weights based on shop tier
        tier_weights = RARITY_WEIGHTS.copy()
        if shop_tier > 1:
            # Decrease common chance, increase rare+ chances for higher tier shops
            tier_weights["common"] = max(10, 50 - (shop_tier * 10))
            tier_weights["uncommon"] = 30 + (shop_tier * 2)
            tier_weights["rare"] = 15 + (shop_tier * 5)
            tier_weights["epic"] = 4 + (shop_tier * 2)
            tier_weights["legendary"] = 1 + shop_tier
            
        logging.debug(f"Shop tier {shop_tier} rarity weights: {tier_weights}")
        
        # Group items by rarity
        items_by_rarity = {}
        for item in all_items:
            rarity = item["rarity"].lower()
            if rarity not in items_by_rarity:
                items_by_rarity[rarity] = []
            items_by_rarity[rarity].append(item)
        
        # Count attempt to avoid infinite loops if there aren't enough unique items
        attempt_count = 0
        max_attempts = item_count * 10  # Increased to ensure we can find items even with bad RNG
        
        # Select random items based on rarity weights
        while len(shop_items) < item_count and attempt_count < max_attempts:
            attempt_count += 1
            
            # Determine rarity based on weights
            rarities = list(tier_weights.keys())
            weights = list(tier_weights.values())
            selected_rarity = random.choices(rarities, weights=weights, k=1)[0]
            
            # If no items of this rarity, try another
            if selected_rarity not in items_by_rarity or not items_by_rarity[selected_rarity]:
                # Try all rarities from highest to lowest
                for rarity in sorted(items_by_rarity.keys(), 
                                     key=lambda r: ["common", "uncommon", "rare", "epic", "legendary"].index(r), 
                                     reverse=True):
                    if items_by_rarity[rarity]:
                        selected_rarity = rarity
                        break
                else:
                    # Skip if still no items found
                    continue
            
            # Get available items of this rarity (items not already selected)
            available_items = [item for item in items_by_rarity[selected_rarity] 
                               if str(item["id"]) not in selected_item_ids]
            
            # If no available items of this rarity, try another rarity
            if not available_items:
                continue
                
            # Select random item of chosen rarity
            item = random.choice(available_items)
            
            # Mark as selected to avoid duplicates
            selected_item_ids.add(str(item["id"]))
            
            # Calculate price with some randomness
            base_price = item["base_price"]
            if base_price >= 10: # Only apply variance if base price is above a threshold
                price_variance = random.uniform(0.8, 1.2)  # 20% variance
                final_price = int(base_price * price_variance)
            else:
                final_price = base_price
            
            # Add item to shop inventory
            shop_items.append({
                "id": str(item["id"]),
                "name": item["name"],
                "description": item["description"],
                "image": item["image"],
                "item_type": item["item_type"],
                "rarity": item["rarity"],
                "price": final_price
            })
        
        # If we couldn't find enough unique items, log a warning
        if len(shop_items) < item_count:
            logging.warning(f"Could only generate {len(shop_items)} unique items for shop (requested {item_count})")
            
        return shop_items
    except Exception as e:
        logging.error(f"Error generating shop inventory: {str(e)}")
        return []

def add_item_to_inventory(event_id: str, team_id: str, item_id: str) -> bool:
    """
    Add an item to a team's inventory
    
    Parameters:
    - event_id: Event ID
    - team_id: Team ID
    - item_id: Item ID to add
    
    Returns:
    - Success flag
    """
    try:
        # Get team and save data
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            logging.error(f"Team not found: {team_id}")
            return False
        
        save = SaveData.from_dict(team.data)
        
        # Get item details from registry or database
        item = get_item_by_id(item_id)
        if not item:
            logging.error(f"Item not found: {item_id}")
            return False
            
        # Create inventory item entry
        item_entry = {
            "id": item_id,
            "name": item["name"],
            "description": item["description"],
            "item_type": item["item_type"],
            "rarity": item["rarity"],
            "uses_remaining": item["uses"],
            "purchased_at": datetime.now().isoformat()
        }
        
        # Add to inventory
        save.itemList.append(item_entry)
        logging.info(f"Added item {item['name']} (ID: {item_id}) to team {team_id} inventory")
        
        # Save changes
        save_team_data(team, save)
        return True
    
    except Exception as e:
        logging.error(f"Error adding item to inventory: {str(e)}")
        return False

def use_item(event_id: str, team_id: str, item_index: int) -> Dict[str, Any]:
    """
    Use/activate an item from a team's inventory
    
    Parameters:
    - event_id: Event ID
    - team_id: Team ID
    - item_index: Index of the item in the team's inventory
    
    Returns:
    - Result dictionary with success flag and messages
    """
    try:
        # Get team and save data
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            logging.error(f"Team not found: {team_id}")
            return {"success": False, "message": "Team not found"}
        
        save = SaveData.from_dict(team.data)

        # Check if there are any pending item activations
        if save.pendingItemActivation:
            logging.warning(f"Pending item activations found for team {team_id}, cannot use item")
            return {"success": False, "message": "Cannot use item while another activation is pending"} 
        
        # Check if item index is valid
        if item_index < 0 or item_index >= len(save.itemList):
            logging.error(f"Invalid item index: {item_index}")
            return {"success": False, "message": "Item not found in inventory"}
        
        # Get item from inventory
        item_entry = save.itemList[item_index]
        item_id = item_entry.get("id")
        
        # Get full item details from registry or database
        item = get_item_by_id(item_id)
        if not item:
            logging.error(f"Item not found in registry or database: {item_id}")
            return {"success": False, "message": "Item not found in registry"}
        
        # Check if item can be used (has uses remaining)
        uses_remaining = item_entry.get("uses_remaining", item["uses"])
        if uses_remaining <= 0:
            logging.warning(f"Item {item['name']} has no uses remaining")
            return {"success": False, "message": "This item has no uses remaining"}
        
        # Check if item has an activation handler
        handler_name = item["activation_handler"]
        if not handler_name or handler_name not in ITEM_HANDLERS:
            logging.error(f"No handler found for item type: {handler_name}")
            return {"success": False, "message": "This item cannot be activated"}
        
        # Call the item handler function
        handler = ITEM_HANDLERS[handler_name]
        result = handler(event_id, team_id, save, item_entry)

        if "error" in result:
            logging.error(f"Error using item {item['name']}: {result['error']}")
            return {"success": False, "message": result["error"]}

        if item.get("requires_selection", False):
            save.pendingItemActivation = {
                "item_id": item_id,
                "item_index": item_index,
                "item_name": item["name"],
                "options": result.get("options", []),
                "effect": result.get("effect", {}),
            }

            save_team_data(team, save)

            return {
                "success": True,
                "requires_selection": True,
                "message": result.get("message", f"used {item['name']} successfully!"),
                "options": result.get("options", []),
                "item_name": item["name"]
            }
        else:
            send_event_notification(event_id, team_id, f"{item['name']} used by {team.name}!", result.get("message", ""))
        
        # Update uses remaining
        save.itemList[item_index]["uses_remaining"] = uses_remaining - 1
        
        # Remove item if no uses remaining
        if save.itemList[item_index]["uses_remaining"] <= 0 and item["uses"] > 0:  # Only remove consumables, not unlimited use items
            logging.info(f"Item {item['name']} used up, removing from inventory")
            if "remove_on_use" not in result or result["remove_on_use"]:
                save.itemList.pop(item_index)
            
        # Save changes
        save_team_data(team, save)
        
        # Return result
        return {
            "success": True, 
            "message": result.get("message", f"{item['name']} used successfully!"),
            "effect": result.get("effect", {}),
            "item_name": item["name"]
        }
        
    except Exception as e:
        logging.error(f"Error using item: {str(e)}")
        return {"success": False, "message": f"Error using item: {str(e)}"}
    
def complete_item_activation(event_id: str, team_id: str, selection_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Complete a two-stage item activation by processing the user's selection
    
    Parameters:
    - event_id: Event ID
    - team_id: Team ID
    - selection_data: Dictionary containing the selected option
    
    Returns:
    - Result dictionary with the outcome of the selection
    """
    try:
        # Get team and save data
        team = EventTeams.query.filter_by(id=team_id, event_id=event_id).first()
        if not team:
            logging.error(f"Team not found: {team_id}")
            return {"success": False, "message": "Team not found"}
        
        save = SaveData.from_dict(team.data)
        
        # Check if there's a pending activation
        if not hasattr(save, 'pendingItemActivation') or not save.pendingItemActivation:
            logging.error(f"No pending item activation for team {team_id}")
            return {"success": False, "message": "No item waiting for your selection"}
        
        pending = save.pendingItemActivation
        item_index = pending["item_index"]
        selection_handler = pending["item_id"] + "_selection"
        
        # Validate that the item still exists in inventory (hasn't been removed somehow)
        if item_index >= len(save.itemList) or save.itemList[item_index]["id"] != pending["item_id"]:
            logging.error(f"Pending item no longer exists in inventory: {pending['item_id']}")
            save.pendingItemActivation = {}
            save_team_data(team, save)
            return {"success": False, "message": "The item you were using is no longer in your inventory"}
        
        # Get the selection handler
        if not selection_handler or selection_handler not in ITEM_HANDLERS:
            logging.error(f"No selection handler found: {selection_handler}")
            save.pendingItemActivation = {}
            save_team_data(team, save)
            return {"success": False, "message": "Unable to process your selection"}
        
        # Call the selection handler with the selected option
        handler = ITEM_HANDLERS[selection_handler]
        result = handler(
            event_id,
            team_id,
            save, 
            save.itemList[item_index],
            selected_value=selection_data.get("selection")
        )
        
        # Get full item details
        item = get_item_by_id(pending["item_id"])
        if not item:
            logging.error(f"Item not found in registry: {pending['item_id']}")
            save.pendingItemActivation = {}
            save_team_data(team, save)
            return {"success": False, "message": "Item definition no longer exists"}
        
        # Update uses remaining
        uses_remaining = save.itemList[item_index].get("uses_remaining", item["uses"]) - 1
        save.itemList[item_index]["uses_remaining"] = uses_remaining
        
        # Remove item if no uses remaining
        if uses_remaining <= 0 and item["uses"] > 0:
            logging.info(f"Item {item['name']} used up, removing from inventory")
            if "remove_on_use" not in result or result["remove_on_use"]:
                save.itemList.pop(item_index)
        
        # Clear the pending activation
        save.pendingItemActivation = {}
        
        # Save changes
        save_team_data(team, save)
        
        send_event_notification(event_id, team_id, f"{item['name']} used by {team.name}!", result.get("message", ""))
        
        # Return result
        return {
            "success": True, 
            "message": result.get("message", f"{item['name']} used successfully!"),
            "effect": result.get("effect", {}),
            "item_name": item["name"]
        }
        
    except Exception as e:
        logging.error(f"Error completing item activation: {str(e)}")
        return {"success": False, "message": f"Error completing item activation: {str(e)}"}
