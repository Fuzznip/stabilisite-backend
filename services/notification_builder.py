from event_handlers.event_handler import NotificationResponse, NotificationAuthor, NotificationField
from models.new_events import Event, Team, Tile
from typing import Optional
import logging

class NotificationBuilder:
    """
    Builds Discord notification responses for event progress.
    """

    @staticmethod
    def build_task_completion_notification(
        event: Event,
        team: Team,
        tile: Tile,
        medal_level: int
    ) -> NotificationResponse:
        """
        Build notification for task completion (no bingo).

        Args:
            event: The event
            team: The team that completed the task
            tile: The tile where task was completed
            medal_level: The medal level achieved (1=bronze, 2=silver, 3=gold)

        Returns:
            NotificationResponse object
        """
        medal_names = {1: 'Bronze', 2: 'Silver', 3: 'Gold'}
        medal_name = medal_names.get(medal_level, 'Unknown')

        # Color based on medal level
        colors = {
            1: 0xCD7F32,  # Bronze
            2: 0xC0C0C0,  # Silver
            3: 0xFFD700   # Gold
        }
        color = colors.get(medal_level, 0xFFD700)

        return NotificationResponse(
            threadId=event.thread_id,
            title=f"{tile.name} - {medal_name} Medal!",
            color=color,
            description=f"The **{team.name}** have completed a {medal_name.lower()} task on {tile.name}!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                ),
                NotificationField(
                    name="Medal Level",
                    value=medal_name,
                    inline=True
                )
            ]
        )

    @staticmethod
    def build_bingo_notification(
        event: Event,
        team: Team,
        bingo_count: int,
        medal_level: int
    ) -> NotificationResponse:
        """
        Build notification for bingo completion.

        Args:
            event: The event
            team: The team that got bingo
            bingo_count: Number of bingos (rows/columns completed)
            medal_level: The medal level of the bingo (1=bronze, 2=silver, 3=gold)

        Returns:
            NotificationResponse object
        """
        medal_names = {1: 'Bronze', 2: 'Silver', 3: 'Gold'}
        medal_name = medal_names.get(medal_level, 'Unknown')

        if bingo_count == 1:
            title = f"{medal_name} Bingo!"
            description = f"The **{team.name}** have completed a row or column at {medal_name.lower()} level!"
            color = 0x00FF00  # Green
        elif bingo_count == 2:
            title = f"Double {medal_name} Bingo!"
            description = f"The **{team.name}** have completed TWO {medal_name.lower()} bingos!"
            color = 0xFF4500  # OrangeRed
        elif bingo_count >= 3:
            title = f"Multiple {medal_name} Bingos!"
            description = f"The **{team.name}** have completed {bingo_count} {medal_name.lower()} bingos!"
            color = 0xFF0000  # Red
        else:
            # Shouldn't happen, but handle gracefully
            title = "Bingo Anomaly"
            description = f"Something unexpected happened with {team.name}'s bingo count: {bingo_count}"
            color = 0xFF00FF  # Magenta
            logging.warning(f"Unexpected bingo_count: {bingo_count} for team {team.id}")

        return NotificationResponse(
            threadId=event.thread_id,
            title=title,
            color=color,
            description=description,
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Total Points",
                    value=str(team.points),
                    inline=True
                ),
                NotificationField(
                    name="Bingo Count",
                    value=str(bingo_count),
                    inline=True
                ),
                NotificationField(
                    name="Medal Level",
                    value=medal_name,
                    inline=True
                )
            ]
        )

    @staticmethod
    def build_challenge_completion_notification(
        event: Event,
        team: Team,
        challenge_name: str,
        current_quantity: int,
        required_quantity: int
    ) -> Optional[NotificationResponse]:
        """
        Build notification for individual challenge progress (optional).
        Can be used for major milestones.

        Args:
            event: The event
            team: The team
            challenge_name: Name of the challenge
            current_quantity: Current progress
            required_quantity: Required to complete

        Returns:
            NotificationResponse object or None if not worth notifying
        """
        # Only notify on completion for now
        if current_quantity < required_quantity:
            return None

        return NotificationResponse(
            threadId=event.thread_id,
            title=f"Challenge Complete: {challenge_name}",
            color=0x00CED1,  # DarkTurquoise
            description=f"The **{team.name}** have completed the {challenge_name} challenge!",
            author=NotificationAuthor(
                name=team.name,
                icon_url=team.image_url
            ),
            fields=[
                NotificationField(
                    name="Progress",
                    value=f"{current_quantity}/{required_quantity}",
                    inline=True
                )
            ]
        )
