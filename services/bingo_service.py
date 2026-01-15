from models.new_events import Event, Team, Tile, TileStatus
from app import db
from typing import Optional
import logging

class BingoService:
    """
    Bingo-specific game logic.
    Detects bingo completions and awards bonus points.
    """

    @staticmethod
    def count_bingos_at_level(
        event_id: str,
        team_id: str,
        medal_level: int
    ) -> int:
        """
        Count how many bingos exist at a specific medal level.
        Does NOT award points - just counts.

        Args:
            event_id: The event ID
            team_id: The team ID
            medal_level: The medal level to check (1, 2, or 3)

        Returns:
            Number of bingos at this medal level
        """
        if medal_level < 1 or medal_level > 3:
            logging.error(f"Invalid medal level: {medal_level}")
            return 0

        # Get all tile statuses for this team in this event
        # Use eager loading to avoid N+1 queries
        from sqlalchemy.orm import joinedload
        tile_statuses = TileStatus.query.join(Tile).options(
            joinedload(TileStatus.tile)
        ).filter(
            Tile.event_id == event_id,
            TileStatus.team_id == team_id
        ).all()

        if not tile_statuses:
            return 0

        # Build 5x5 grid of medal levels
        grid = [[0]*5 for _ in range(5)]
        for ts in tile_statuses:
            # Access the eagerly loaded tile relationship (no additional query)
            if ts.tile:
                row, col = ts.tile.index // 5, ts.tile.index % 5
                grid[row][col] = ts.tasks_completed

        # Count bingos at the medal level
        bingo_count = 0

        # Check rows: ALL tiles in row must have >= medal_level
        for row in grid:
            if all(level >= medal_level for level in row):
                bingo_count += 1

        # Check columns: ALL tiles in column must have >= medal_level
        for col in range(5):
            if all(grid[row][col] >= medal_level for row in range(5)):
                bingo_count += 1

        return bingo_count

    @staticmethod
    def check_and_award_bingos(
        event_id: str,
        team_id: str,
        new_medal_level: int
    ) -> int:
        """
        DEPRECATED: Use count_bingos_at_level instead.
        This method is kept for backward compatibility but should not be used
        as it doesn't handle delta-based awarding correctly.

        Args:
            event_id: The event ID
            team_id: The team ID
            new_medal_level: The medal level that was just achieved (1, 2, or 3)

        Returns:
            Number of bingos completed at this medal level
        """
        logging.warning("check_and_award_bingos is deprecated. Use count_bingos_at_level with delta logic instead.")

        bingo_count = BingoService.count_bingos_at_level(event_id, team_id, new_medal_level)

        # Award points for bingos
        if bingo_count > 0:
            team = Team.query.filter_by(id=team_id).first()
            if team:
                points_awarded = bingo_count * 15
                team.points += points_awarded
                db.session.commit()
                logging.info(f"Team {team_id} awarded {points_awarded} points for {bingo_count} bingo(s) at medal level {new_medal_level}")

        return bingo_count

    @staticmethod
    def get_board_state(event_id: str, team_id: str) -> list[dict]:
        """
        Get the current board state for a team.

        Args:
            event_id: The event ID
            team_id: The team ID

        Returns:
            List of tile states with medal levels
        """
        tiles = Tile.query.filter_by(event_id=event_id).order_by(Tile.index).all()
        board_state = []

        for tile in tiles:
            tile_status = TileStatus.query.filter_by(
                team_id=team_id,
                tile_id=tile.id
            ).first()

            board_state.append({
                'index': tile.index,
                'name': tile.name,
                'tasks_completed': tile_status.tasks_completed if tile_status else 0,
                'medal_level': BingoService._get_medal_name(tile_status.tasks_completed if tile_status else 0)
            })

        return board_state

    @staticmethod
    def _get_medal_name(tasks_completed: int) -> str:
        """Convert tasks_completed number to medal name"""
        medal_map = {0: 'none', 1: 'bronze', 2: 'silver', 3: 'gold'}
        return medal_map.get(tasks_completed, 'none')

    @staticmethod
    def check_previous_bingos(event_id: str, team_id: str, medal_level: int) -> bool:
        """
        Check if team already completed bingos at a specific medal level.
        Used to determine if current bingos are "new".

        Args:
            event_id: The event ID
            team_id: The team ID
            medal_level: Medal level to check (1, 2, or 3)

        Returns:
            True if bingos existed at this level before, False otherwise
        """
        tile_statuses = TileStatus.query.join(Tile).filter(
            Tile.event_id == event_id,
            TileStatus.team_id == team_id
        ).all()

        if not tile_statuses:
            return False

        # Build grid
        grid = [[0]*5 for _ in range(5)]
        for ts in tile_statuses:
            tile = Tile.query.filter_by(id=ts.tile_id).first()
            if tile:
                row, col = tile.index // 5, tile.index % 5
                grid[row][col] = ts.tasks_completed

        # Check rows
        for row in grid:
            if all(level >= medal_level for level in row):
                return True

        # Check columns
        for col in range(5):
            if all(grid[row][col] >= medal_level for row in range(5)):
                return True

        return False

    @staticmethod
    def get_leaderboard(event_id: str) -> list[dict]:
        """
        Get team leaderboard for an event, sorted by points.

        Args:
            event_id: The event ID

        Returns:
            List of teams with their scores
        """
        teams = Team.query.filter_by(event_id=event_id).order_by(Team.points.desc()).all()

        leaderboard = []
        for rank, team in enumerate(teams, 1):
            leaderboard.append({
                'rank': rank,
                'team_id': str(team.id),
                'name': team.name,
                'points': team.points,
                'image_url': team.image_url
            })

        return leaderboard
