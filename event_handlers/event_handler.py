import logging

class EventSubmission:
    def __init__(self, rsn: str, id: str | None, trigger: str, source: str | None, quantity: int | None, totalValue: int | None, img_path: str | None, type: str | None, request_id: str | None = None) -> None:
        self.rsn = rsn
        self.id = id
        self.trigger = trigger
        self.source = source
        self.quantity = quantity
        self.totalValue = totalValue
        self.img_path = img_path
        self.type = type
        self.request_id = request_id

    rsn: str
    id: str | None
    trigger: str
    source: str | None
    quantity: int | None
    totalValue: int | None
    img_path: str | None
    type: str | None
    request_id: str | None

class NotificationAuthor:
    def __init__(self, name: str, icon_url: str | None = None, url: str | None = None) -> None:
        self.name = name
        self.icon_url = icon_url
        self.url = url

    name: str
    icon_url: str | None = None
    url: str | None = None

    def to_dict(self):
        return {
            "name": self.name,
            "icon_url": self.icon_url,
            "url": self.url,
        }

class NotificationField:
    def __init__(self, name: str, value: str, inline: bool = False) -> None:
        self.name = name
        self.value = value
        self.inline = inline

    name: str
    value: str
    inline: bool = False

    def to_dict(self):
        return {
            "name": self.name,
            "value": self.value,
            "inline": self.inline,
        }

class NotificationResponse:
    def __init__(self, threadId: str | None, title: str | None, color: int | None = 0x992D22, description: str | None = None, thumbnailImage: str | None = None, author: NotificationAuthor | None = None, fields: list[NotificationField] | None = None) -> None:
        self.threadId = threadId
        self.title = title
        self.color = color
        self.description = description
        self.thumbnailImage = thumbnailImage
        self.author = author
        self.fields = fields

    threadId: str | None
    title: str | None
    color: int = 0x992D22  # Default color (dark red)
    description: str | None
    thumbnailImage: str | None
    author: NotificationAuthor | None
    fields: list[NotificationField] | None

    def to_dict(self):
        return {
            "threadId": self.threadId,
            "title": self.title,
            "color": self.color,
            "description": self.description,
            "thumbnailImage": self.thumbnailImage,
            "author": self.author.to_dict() if self.author else None,
            "fields": [field.to_dict() for field in self.fields] if self.fields else [],
        }

class EventHandler:
    handlers = []

    @classmethod
    def register_handler(cls, handler):
        # make sure the handler is a function that takes an EventSubmission object and returns a NotificationResponse object
        if not callable(handler):
            raise ValueError("Handler must be a callable function")
        if not hasattr(handler, "__annotations__"):
            raise ValueError("Handler must have type annotations")
        if "submission" not in handler.__annotations__:
            raise ValueError("Handler must accept an EventSubmission object as the first argument")
        if "return" not in handler.__annotations__:
            raise ValueError("Handler must return a NotificationResponse object")
        if handler.__annotations__["submission"] != EventSubmission:
            raise ValueError("Handler must accept an EventSubmission object as the first argument")
        if handler.__annotations__["return"] != list[NotificationResponse]:
            raise ValueError("Handler must return a list of NotificationResponse objects")
        
        # Register the handler
        cls.handlers.append(handler)
        logging.info(f"Handler {handler.__name__} registered successfully.")

    @classmethod
    def handle_event(cls, data: EventSubmission):
        notifications: list[NotificationResponse] = []
        for handler in cls.handlers:
            try:
                responses: list[NotificationResponse] = handler(data)
                if not responses:
                    continue
                
                for notif in responses:
                    notifications.append(notif.to_dict())
            except Exception as e:
                logging.error(f"Error in handler {handler.__name__}: {e}", exc_info=True)
        return {"notifications": notifications}
