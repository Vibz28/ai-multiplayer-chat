from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import boto3
from botocore.exceptions import ClientError


class MappingNotFoundError(Exception):
    """Raised when an application mapping cannot be found."""


class MappingConflictError(Exception):
    """Raised when a thread assignment conflicts with existing mapping state."""


@dataclass(frozen=True)
class MappingRecord:
    application_id: str
    profile_id: str | None
    langgraph_thread_id: str | None
    created_at: datetime
    updated_at: datetime


class MappingRepository(Protocol):
    def ensure_table(self) -> None:
        ...

    def ping(self) -> bool:
        ...

    def create_application(self, application_id: str, profile_id: str | None) -> MappingRecord:
        ...

    def get_mapping(self, application_id: str) -> MappingRecord | None:
        ...

    def assign_thread(self, application_id: str, langgraph_thread_id: str) -> MappingRecord:
        ...


class DynamoDBMappingRepository:
    def __init__(
        self,
        *,
        table_name: str,
        endpoint_url: str,
        region_name: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._table_name = table_name
        self._dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        self._table = self._dynamodb.Table(table_name)

    @property
    def table_name(self) -> str:
        return self._table_name

    def ensure_table(self) -> None:
        try:
            self._table.load()
            return
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "ResourceNotFoundException":
                raise

        self._dynamodb.create_table(
            TableName=self._table_name,
            KeySchema=[{"AttributeName": "application_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "application_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = self._dynamodb.meta.client.get_waiter("table_exists")
        waiter.wait(TableName=self._table_name)

    def ping(self) -> bool:
        self._table.load()
        return True

    def create_application(self, application_id: str, profile_id: str | None) -> MappingRecord:
        now = datetime.now(UTC).isoformat()
        item = {
            "application_id": application_id,
            "profile_id": profile_id,
            "langgraph_thread_id": None,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(application_id)",
        )
        return self._to_record(item)

    def get_mapping(self, application_id: str) -> MappingRecord | None:
        response = self._table.get_item(Key={"application_id": application_id})
        item = response.get("Item")
        if not item:
            return None
        return self._to_record(item)

    def assign_thread(self, application_id: str, langgraph_thread_id: str) -> MappingRecord:
        now = datetime.now(UTC).isoformat()
        try:
            response = self._table.update_item(
                Key={"application_id": application_id},
                UpdateExpression="SET langgraph_thread_id=:thread_id, updated_at=:updated_at",
                ExpressionAttributeValues={
                    ":thread_id": langgraph_thread_id,
                    ":updated_at": now,
                    ":existing_thread": langgraph_thread_id,
                    ":null_type": "NULL",
                },
                ConditionExpression=(
                    "attribute_exists(application_id) AND "
                    "("
                    "attribute_not_exists(langgraph_thread_id) "
                    "OR attribute_type(langgraph_thread_id, :null_type) "
                    "OR langgraph_thread_id = :existing_thread"
                    ")"
                ),
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise MappingConflictError(application_id) from exc
            raise

        attributes = response.get("Attributes")
        if not attributes:
            raise MappingNotFoundError(application_id)
        return self._to_record(attributes)

    @staticmethod
    def _to_record(item: dict[str, str | None]) -> MappingRecord:
        return MappingRecord(
            application_id=str(item["application_id"]),
            profile_id=item.get("profile_id"),
            langgraph_thread_id=item.get("langgraph_thread_id"),
            created_at=datetime.fromisoformat(str(item["created_at"])),
            updated_at=datetime.fromisoformat(str(item["updated_at"])),
        )
