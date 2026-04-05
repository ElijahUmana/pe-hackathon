import datetime

from peewee import AutoField, CharField, DateTimeField, ForeignKeyField, TextField

from app.database import BaseModel
from app.models.url import URL
from app.models.user import User


class Event(BaseModel):
    id = AutoField()
    url_id = ForeignKeyField(URL, backref="events", column_name="url_id")
    user_id = ForeignKeyField(User, backref="events", column_name="user_id", null=True)
    event_type = CharField()
    timestamp = DateTimeField(default=datetime.datetime.utcnow)
    details = TextField(null=True)

    class Meta:
        table_name = "events"
