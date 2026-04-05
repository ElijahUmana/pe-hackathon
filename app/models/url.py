import datetime

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    TextField,
)

from app.database import BaseModel
from app.models.user import User


class URL(BaseModel):
    id = AutoField()
    user_id = ForeignKeyField(User, backref="urls", column_name="user_id", null=True)
    short_code = CharField(max_length=20, unique=True)
    original_url = TextField()
    title = CharField(null=True)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        table_name = "urls"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)
