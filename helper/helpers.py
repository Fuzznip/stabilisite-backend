from sqlalchemy.inspection import inspect
import json
import decimal
from datetime import date, datetime
from uuid import UUID

class Serializer:
    def serialize(self):
        data = {}

        mapper = inspect(self).mapper
        for column in mapper.columns:
            value = getattr(self, column.key)

            if isinstance(value, UUID):
                value = str(value)
            elif isinstance(value, (datetime, date)):
                value = value.isoformat()

            data[column.key] = value

        return data

    @staticmethod
    def serialize_list(items):
        return [item.serialize() for item in items]


# Used to Serialize the models
class ModelEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return obj.hex
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)
