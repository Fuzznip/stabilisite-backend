from app import app, db
from helper.helpers import ModelEncoder
from flask import request
from event_handlers.event_handler import EventHandler, EventSubmission  # Import the centralized event handler system
import json

#input:
# {
#     "rsn": player,
#     "id": discordId,
#     "trigger": trigger,
#     "source": source,
#     "quantity": quantity,
#     "totalValue": totalValue,
#     "type": type,
# }

#reponse:
# title=f"{player}: {trigger} from {source}",
# thumbnailImage="https://i.imgur.com/4LdSYto.jpeg",
# author=DiscordEmbedAuthor(name="ToA Suckers"),
# description=f"They have been awarded 10 coins and a 4 sided die!",
# fields=[
#     DiscordEmbedField(name="Stars", value="6", inline=True),
#     DiscordEmbedField(name="Coins", value="144", inline=True),
#     DiscordEmbedField(name="Island", value="Island of Stone", inline=True),
# ]

@app.route("/events/submit", methods=['POST'])
def submit_event():
    data = request.get_json()
    if data is None:
        return "No JSON received", 400

    # Convert the incoming data to an EventSubmission object
    event_submission = EventSubmission(
        rsn=data.get("rsn"),
        id=data.get("id"),
        trigger=data.get("trigger"),
        source=data.get("source"),
        quantity=data.get("quantity"),
        totalValue=data.get("totalValue"),
        img_path=data.get("img_path"),
        type=data.get("type")
    )

    # Pass the submission data to the centralized event handler system
    response = EventHandler.handle_event(event_submission)

    return json.dumps(response, cls=ModelEncoder)
