from app import db
from typing import Type, Optional, Dict, Any, List
from sqlalchemy.exc import IntegrityError
import logging

class CRUDService:
    """Generic CRUD service for database operations"""

    @staticmethod
    def create(model_class: Type[db.Model], data: Dict[str, Any]) -> Optional[db.Model]:
        """
        Create a new record

        Args:
            model_class: The SQLAlchemy model class
            data: Dictionary of field values

        Returns:
            Created model instance or None if error
        """
        try:
            instance = model_class(**data)
            db.session.add(instance)
            db.session.commit()
            return instance
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"IntegrityError creating {model_class.__name__}: {e}")
            return None
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating {model_class.__name__}: {e}")
            return None

    @staticmethod
    def get_by_id(model_class: Type[db.Model], id: str) -> Optional[db.Model]:
        """
        Get a single record by ID

        Args:
            model_class: The SQLAlchemy model class
            id: The record ID

        Returns:
            Model instance or None if not found
        """
        try:
            return model_class.query.filter_by(id=id).first()
        except Exception as e:
            logging.error(f"Error getting {model_class.__name__} by id {id}: {e}")
            return None

    @staticmethod
    def get_all(
        model_class: Type[db.Model],
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        per_page: int = 50,
        order_by: Optional[str] = None
    ) -> tuple[List[db.Model], int]:
        """
        Get all records with optional filtering and pagination

        Args:
            model_class: The SQLAlchemy model class
            filters: Dictionary of field:value pairs to filter by
            page: Page number (1-indexed)
            per_page: Number of records per page
            order_by: Field name to order by (prefix with '-' for descending)

        Returns:
            Tuple of (records list, total count)
        """
        try:
            query = model_class.query

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(model_class, key):
                        query = query.filter(getattr(model_class, key) == value)

            # Get total count before pagination
            total = query.count()

            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    field_name = order_by[1:]
                    if hasattr(model_class, field_name):
                        query = query.order_by(getattr(model_class, field_name).desc())
                else:
                    if hasattr(model_class, order_by):
                        query = query.order_by(getattr(model_class, order_by))

            # Apply pagination
            records = query.paginate(page=page, per_page=per_page, error_out=False).items

            return records, total
        except Exception as e:
            logging.error(f"Error getting all {model_class.__name__}: {e}")
            return [], 0

    @staticmethod
    def update(model_class: Type[db.Model], id: str, data: Dict[str, Any]) -> Optional[db.Model]:
        """
        Update a record

        Args:
            model_class: The SQLAlchemy model class
            id: The record ID
            data: Dictionary of fields to update

        Returns:
            Updated model instance or None if not found/error
        """
        try:
            instance = model_class.query.filter_by(id=id).first()
            if not instance:
                return None

            for key, value in data.items():
                if hasattr(instance, key) and key not in ['id', 'created_at']:
                    setattr(instance, key, value)

            db.session.commit()
            return instance
        except IntegrityError as e:
            db.session.rollback()
            logging.error(f"IntegrityError updating {model_class.__name__} {id}: {e}")
            return None
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating {model_class.__name__} {id}: {e}")
            return None

    @staticmethod
    def delete(model_class: Type[db.Model], id: str) -> bool:
        """
        Delete a record

        Args:
            model_class: The SQLAlchemy model class
            id: The record ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            instance = model_class.query.filter_by(id=id).first()
            if not instance:
                return False

            db.session.delete(instance)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deleting {model_class.__name__} {id}: {e}")
            return False
