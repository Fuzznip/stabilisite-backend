from models.models import Users
from sqlalchemy import func, text


def resolve_user(rsn: str | None, discord_id: str | None) -> Users | None:
    """Find the member a submission belongs to, cheapest lookup first.

    Underscores and dashes are normalized to spaces because WoM, Dink and the
    game itself treat them as equivalent in a display name.

    Order matters: runescape_name and discord_id are indexed lookups, while the
    alt_names match unnests an array on every row, so it only runs last.
    """
    if rsn:
        normalized = rsn.replace("_", " ").replace("-", " ")
        user = Users.query.filter(
            func.lower(func.replace(func.replace(Users.runescape_name, "_", " "), "-", " ")) == normalized.lower()
        ).first()
        if user:
            return user

    if discord_id:
        user = Users.query.filter_by(discord_id=discord_id).first()
        if user:
            return user

    if rsn:
        return Users.query.filter(
            text("lower(replace(replace(:rsn, '_', ' '), '-', ' ')) = ANY(SELECT lower(replace(replace(x, '_', ' '), '-', ' ')) FROM unnest(alt_names) x)")
        ).params(rsn=rsn).first()

    return None
