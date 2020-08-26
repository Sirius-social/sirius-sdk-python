import json
from abc import ABC, abstractmethod
from typing import Optional, List

from sirius_sdk.base import JsonSerializable


class RetrieveRecordOptions(JsonSerializable):

    def __init__(self, retrieve_type: bool=False, retrieve_value: bool=False, retrieve_tags: bool=False):
        self.retrieve_type = retrieve_type
        self.retrieve_value = retrieve_value
        self.retrieve_tags = retrieve_tags

    def check_all(self):
        self.retrieve_type = True
        self.retrieve_value = True
        self.retrieve_tags = True

    def to_json(self):
        options = dict()
        if self.retrieve_type:
            options['retrieveType'] = self.retrieve_type
        if self.retrieve_value:
            options['retrieveValue'] = self.retrieve_value
        if self.retrieve_tags:
            options['retrieveTags'] = self.retrieve_tags
        return options

    def serialize(self):
        return json.dumps(self.to_json())

    def deserialize(self, buffer: str):
        data = json.loads(buffer)
        self.retrieve_type = data.get('retrieveType', False)
        self.retrieve_value = data.get('retrieveValue', False)
        self.retrieve_tags = data.get('retrieveTags', False)


class AbstractNonSecrets(ABC):

    @abstractmethod
    async def add_wallet_record(self, type_: str, id_: str, value: str, tags: dict=None) -> None:
        """
        Create a new non-secret record in the wallet

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param value: the value of record
        :param tags: the record tags used for search and storing meta information as json:
           {
             "tagName1": <str>, // string tag (will be stored encrypted)
             "tagName2": <str>, // string tag (will be stored encrypted)
             "~tagName3": <str>, // string tag (will be stored un-encrypted)
             "~tagName4": <str>, // string tag (will be stored un-encrypted)
           }
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def update_wallet_record_value(self, type_: str, id_: str, value: str) -> None:
        """
        Update a non-secret wallet record value

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param value: the value of record
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def update_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        """
        Update a non-secret wallet record value

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param tags: ags_json: the record tags used for search and storing meta information as json:
           {
             "tagName1": <str>, // string tag (will be stored encrypted)
             "tagName2": <str>, // string tag (will be stored encrypted)
             "~tagName3": <str>, // string tag (will be stored un-encrypted)
             "~tagName4": <str>, // string tag (will be stored un-encrypted)
           }
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def add_wallet_record_tags(self, type_: str, id_: str, tags: dict) -> None:
        """
        Add new tags to the wallet record

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param tags: ags_json: the record tags used for search and storing meta information as json:
           {
             "tagName1": <str>, // string tag (will be stored encrypted)
             "tagName2": <str>, // string tag (will be stored encrypted)
             "~tagName3": <str>, // string tag (will be stored un-encrypted)
             "~tagName4": <str>, // string tag (will be stored un-encrypted)
           }
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def delete_wallet_record_tags(self, type_: str, id_: str, tag_names: List[str]) -> None:
        """
        Add new tags to the wallet record

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param tag_names: the list of tag names to remove from the record as json array: ["tagName1", "tagName2", ...]
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def delete_wallet_record(self, type_: str, id_: str) -> None:
        """
        Delete an existing wallet record in the wallet

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :return: None
        """
        raise NotImplemented

    @abstractmethod
    async def get_wallet_record(self, type_: str, id_: str, options: RetrieveRecordOptions) -> Optional[dict]:
        """
        Get an wallet record by id

        :param type_: allows to separate different record types collections
        :param id_: the id of record
        :param options:
          {
            retrieveType: (optional, false by default) Retrieve record type,
            retrieveValue: (optional, true by default) Retrieve record value,
            retrieveTags: (optional, true by default) Retrieve record tags
          }
        :return: wallet record json:
         {
           id: "Some id",
           type: "Some type", // present only if retrieveType set to true
           value: "Some value", // present only if retrieveValue set to true
           tags: <tags json>, // present only if retrieveTags set to true
         }
        """
        raise NotImplemented

    @abstractmethod
    async def wallet_search(self, type_: str, query: dict, options: RetrieveRecordOptions, limit: int=1) -> (List[dict],int):
        """
        Search for wallet records

        :param type_: allows to separate different record types collections
        :param query: MongoDB style query to wallet record tags:
          {
            "tagName": "tagValue",
            $or: {
              "tagName2": { $regex: 'pattern' },
              "tagName3": { $gte: '123' },
            },
          }
        :param options:
          {
            retrieveRecords: (optional, true by default) If false only "counts" will be calculated,
            retrieveTotalCount: (optional, false by default) Calculate total count,
            retrieveType: (optional, false by default) Retrieve record type,
            retrieveValue: (optional, true by default) Retrieve record value,
            retrieveTags: (optional, true by default) Retrieve record tags,
          }
        :param limit: max record count to retrieve
        :return: wallet records json:
         {
           totalCount: <str>, // present only if retrieveTotalCount set to true
           records: [{ // present only if retrieveRecords set to true
               id: "Some id",
               type: "Some type", // present only if retrieveType set to true
               value: "Some value", // present only if retrieveValue set to true
               tags: <tags json>, // present only if retrieveTags set to true
           }],
         }
        """
        raise NotImplemented
