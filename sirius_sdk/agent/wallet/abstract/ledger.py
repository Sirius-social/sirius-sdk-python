import json
from enum import Enum
from abc import ABC, abstractmethod
from typing import Optional, List, Any


class NYMRole(Enum):

    COMMON_USER = (None, 'null')
    TRUSTEE = (0, 'TRUSTEE')
    STEWARD = (2, 'STEWARD')
    TRUST_ANCHOR = (101, 'TRUST_ANCHOR')
    NETWORK_MONITOR = (201, 'NETWORK_MONITOR')
    RESET = (None, '')

    def serialize(self):
        _, role_name = self.value
        return role_name

    @staticmethod
    def deserialize(buffer: str):
        role_name = buffer
        if role_name == 'null':
            return NYMRole.COMMON_USER
        elif role_name == 'TRUSTEE':
            return NYMRole.TRUSTEE
        elif role_name == 'STEWARD':
            return NYMRole.STEWARD
        elif role_name == 'TRUST_ANCHOR':
            return NYMRole.TRUST_ANCHOR
        elif role_name == 'NETWORK_MONITOR':
            return NYMRole.NETWORK_MONITOR
        elif role_name == '':
            return NYMRole.RESET
        else:
            raise RuntimeError('Unexpected value "%s"' % buffer)


class PoolAction(Enum):

    POOL_RESTART = 'POOL_RESTART'
    GET_VALIDATOR_INFO = 'GET_VALIDATOR_INFO'

    def serialize(self):
        return self.value

    @staticmethod
    def deserialize(buffer: str):
        if buffer == 'POOL_RESTART':
            return PoolAction.POOL_RESTART
        elif buffer == 'GET_VALIDATOR_INFO':
            return PoolAction.GET_VALIDATOR_INFO
        else:
            raise RuntimeError('Unexpected value "%s"' % buffer)


class AbstractLedger(ABC):

    @abstractmethod
    async def read_nym(self, pool_name: str, submitter_did: Optional[str], target_did: str) -> (bool, dict):
        """
         Builds a GET_NYM request. Request to get information about a DID (NYM).

        :param pool_name: Ledger pool.
        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :return: result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def read_attribute(self, pool_name: str, submitter_did: Optional[str], target_did: str, name: str) -> (bool, dict):
        """
        Builds a GET_ATTRIB request. Request to get information about an Attribute for the specified DID.

        :param pool_name: Ledger
        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param name: attribute name.
        :return: Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def write_nym(
            self, pool_name: str, submitter_did: str, target_did: str,
            ver_key: str=None, alias: str=None, role: NYMRole=None
    ) -> (bool, dict):
        """
        Builds a NYM request.

        :param pool_name: Ledger pool.
        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param ver_key: Target identity verification key as base58-encoded string.
        :param alias: NYM's alias.
        :param role: Role of a user NYM record:
                     null (common USER)
                     TRUSTEE
                     STEWARD
                     TRUST_ANCHOR
                     ENDORSER - equal to TRUST_ANCHOR that will be removed soon
                     NETWORK_MONITOR
                     empty string to reset role
        :return: success, result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def register_schema(self, pool_name: str, submitter_did: str, data: dict) -> (bool, dict):
        """
        Builds a SCHEMA request. Request to add Credential's schema.

        :param pool_name: Ledger
        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: Schema data
            {
                id: identifier of schema
                attrNames: array of attribute name strings
                name: schema's name string
                version: schema's version string,
                ver: version of the Schema json
            }
        :return: success, Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def register_cred_def(self, pool_name: str, submitter_did: str, data: dict) -> (bool, dict):
        """
        Builds an CRED_DEF request. Request to add a credential definition (in particular, public key),
        that Issuer creates for a particular Credential Schema.

        :param pool_name: Ledger
        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: credential definition json
                     {
                         id: string - identifier of credential definition
                         schemaId: string - identifier of stored in ledger schema
                         type: string - type of the credential definition. CL is the only supported type now.
                         tag: string - allows to distinct between credential definitions for the same issuer and schema
                         value: Dictionary with Credential Definition's data: {
                             primary: primary credential public key,
                             Optional<revocation>: revocation credential public key
                         },
                         ver: Version of the CredDef json
                     }
        :return: success, Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def write_attribute(
            self, pool_name: str, submitter_did: Optional[str], target_did: str, name: str, value: Any
    ) -> (bool, dict):
        """
        Builds an ATTRIB request. Request to add attribute to a NYM record.

        :param pool_name: Ledger
        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param name: attribute name
        :param value: attribute value
        :return: Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def sign_and_submit_request(self, pool_name: str, submitter_did: str, request: dict) -> dict:
        """
        Signs and submits request message to validator pool.

        Adds submitter information to passed request json, signs it with submitter
        sign key (see wallet_sign), and sends signed request message
        to validator pool (see write_request).

        :param pool_name: Ledger pool.
        :param submitter_did: Id of Identity stored in secured Wallet.
        :param request: Request data json.
        :return: Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def submit_request(self, pool_name: str, request: dict) -> dict:
        """
        Publishes request message to validator pool (no signing, unlike sign_and_submit_request).
        The request is sent to the validator pool as is. It's assumed that it's already prepared.

        :param pool_name: Ledger pool.
        :param request: Request data json.
        :return: Request result
        """
        raise NotImplemented

    @abstractmethod
    async def submit_action(self, pool_name: str, request: dict, nodes: List[str]=None, timeout: int=None) -> dict:
        """
        Send action to particular nodes of validator pool.

        The list of requests can be send:
            POOL_RESTART
            GET_VALIDATOR_INFO

        The request is sent to the nodes as is. It's assumed that it's already prepared.

        :param pool_name: Ledger pool.
        :param request: Request data json.
        :param nodes: (Optional) List of node names to send the request.
               ["Node1", "Node2",...."NodeN"]
        :param timeout: (Optional) Time to wait respond from nodes (override the default timeout) (in sec).
        :return: Request result as json.
        """
        raise NotImplemented

    @abstractmethod
    async def sign_request(self, submitter_did: str, request: dict) -> dict:
        """
        Signs request message.

        Adds submitter information to passed request json, signs it with submitter
        sign key (see wallet_sign).

        :param submitter_did: Id of Identity stored in secured Wallet.
        :param request: Request data json.
        :return: Signed request json.
        """
        raise NotImplemented

    @abstractmethod
    async def multi_sign_request(self, submitter_did: str, request: dict) -> dict:
        """
        Multi signs request message.

        Adds submitter information to passed request json, signs it with submitter
        sign key (see wallet_sign).

        :param submitter_did: Id of Identity stored in secured Wallet.
        :param request: Request data json.
        :return: Signed request json.
        """
        raise NotImplemented

    @abstractmethod
    async def build_get_ddo_request(self, submitter_did: Optional[str], target_did: str) -> dict:
        """
        Builds a request to get a DDO.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param target_did: Id of Identity stored in secured Wallet.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_nym_request(
            self, submitter_did: str, target_did: str, ver_key:str=None,
            alias: str=None, role: NYMRole=None
    ) -> dict:
        """
        Builds a NYM request.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param ver_key: Target identity verification key as base58-encoded string.
        :param alias: NYM's alias.
        :param role: Role of a user NYM record:
                                 null (common USER)
                                 TRUSTEE
                                 STEWARD
                                 TRUST_ANCHOR
                                 ENDORSER - equal to TRUST_ANCHOR that will be removed soon
                                 NETWORK_MONITOR
                                 empty string to reset role
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_attrib_request(self,
            submitter_did: str, target_did: str, xhash: str=None, raw: dict=None, enc: str=None
    ) -> dict:
        """
        Builds an ATTRIB request. Request to add attribute to a NYM record.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param xhash: (Optional) Hash of attribute data.
        :param raw: (Optional) Json, where key is attribute name and value is attribute value.
        :param enc: (Optional) Encrypted value attribute data.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_attrib_request(
            self, submitter_did: Optional[str], target_did: str, raw: str=None, xhash: str=None, enc: str=None
    ) -> dict:
        """
        Builds a GET_ATTRIB request. Request to get information about an Attribute for the specified DID.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :param xhash: (Optional) Requested attribute name.
        :param raw: (Optional) Requested attribute hash.
        :param enc: (Optional) Requested attribute encrypted value.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_nym_request(self, submitter_did: Optional[str], target_did: str) -> dict:
        """
        Builds a GET_NYM request. Request to get information about a DID (NYM).

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param target_did: Target DID as base58-encoded string for 16 or 32 bit DID value.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_nym_response(self, response: Any) -> dict:
        """
        Parse a GET_NYM response to get NYM data.

        :param response: response on GET_NYM request.
        :return: NYM data
        {
            did: DID as base58-encoded string for 16 or 32 bit DID value.
            verkey: verification key as base58-encoded string.
            role: Role associated number
                                    null (common USER)
                                    0 - TRUSTEE
                                    2 - STEWARD
                                    101 - TRUST_ANCHOR
                                    101 - ENDORSER - equal to TRUST_ANCHOR that will be removed soon
                                    201 - NETWORK_MONITOR
        }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_schema_request(self, submitter_did: str, data: dict) -> dict:
        """
        Builds a SCHEMA request. Request to add Credential's schema.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: Credential schema.
                     {
                         id: identifier of schema
                         attrNames: array of attribute name strings (the number of attributes should be less or equal than 125)
                         name: Schema's name string
                         version: Schema's version string,
                         ver: Version of the Schema json
                     }
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_schema_request(self, submitter_did: Optional[str], id_: str) -> dict:
        """
        Builds a GET_SCHEMA request. Request to get Credential's Schema.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param id_: Schema Id in ledger
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_schema_response(self, get_schema_response: dict) -> (str, dict):
        """
        Parse a GET_SCHEMA response to get Schema in the format compatible with Anoncreds API

        :param get_schema_response: response of GET_SCHEMA request.
        :return: Schema Id and Schema json.
         {
             id: identifier of schema
             attrNames: array of attribute name strings
             name: Schema's name string
             version: Schema's version string
             ver: Version of the Schema json
         }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_cred_def_request(self, submitter_did: str, data: dict) -> dict:
        """
        Builds an CRED_DEF request. Request to add a credential definition (in particular, public key),
        that Issuer creates for a particular Credential Schema.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: credential definition json
                     {
                         id: string - identifier of credential definition
                         schemaId: string - identifier of stored in ledger schema
                         type: string - type of the credential definition. CL is the only supported type now.
                         tag: string - allows to distinct between credential definitions for the same issuer and schema
                         value: Dictionary with Credential Definition's data: {
                             primary: primary credential public key,
                             Optional<revocation>: revocation credential public key
                         },
                         ver: Version of the CredDef json
                     }
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_cred_def_request(self, submitter_did: Optional[str], id_: str) -> dict:
        """
        Builds a GET_CRED_DEF request. Request to get a credential definition (in particular, public key),
        that Issuer creates for a particular Credential Schema.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param id_: Credential Definition Id in ledger.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_cred_def_response(self, get_cred_def_response: dict) -> (str, dict):
        """
        Parse a GET_CRED_DEF response to get Credential Definition in the format compatible with Anoncreds API.

        :param get_cred_def_response: response of GET_CRED_DEF request.
        :return: Credential Definition Id and Credential Definition json.
          {
              id: string - identifier of credential definition
              schemaId: string - identifier of stored in ledger schema
              type: string - type of the credential definition. CL is the only supported type now.
              tag: string - allows to distinct between credential definitions for the same issuer and schema
              value: Dictionary with Credential Definition's data: {
                  primary: primary credential public key,
                  Optional<revocation>: revocation credential public key
              },
              ver: Version of the Credential Definition json
          }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_node_request(self, submitter_did: str, target_did: str, data: dict) -> dict:
        """
        Builds a NODE request. Request to add a new node to the pool, or updates existing in the pool.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param target_did: Target Node's DID.  It differs from submitter_did field.
        :param data: Data associated with the Node:
          {
              alias: string - Node's alias
              blskey: string - (Optional) BLS multi-signature key as base58-encoded string.
              blskey_pop: string - (Optional) BLS key proof of possession as base58-encoded string.
              client_ip: string - (Optional) Node's client listener IP address.
              client_port: string - (Optional) Node's client listener port.
              node_ip: string - (Optional) The IP address other Nodes use to communicate with this Node.
              node_port: string - (Optional) The port other Nodes use to communicate with this Node.
              services: array<string> - (Optional) The service of the Node. VALIDATOR is the only supported one now.
          }
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_validator_info_request(self, submitter_did: str) -> dict:
        """
        Builds a GET_VALIDATOR_INFO request.
        :param submitter_did: Id of Identity stored in secured Wallet.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_txn_request(self, submitter_did: Optional[str], ledger_type: Optional[str], seq_no: int) -> dict:
        """
        Builds a GET_TXN request. Request to get any transaction by its seq_no.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param ledger_type: (Optional) type of the ledger the requested transaction belongs to:
            DOMAIN - used default,
            POOL,
            CONFIG
            any number
        :param seq_no: requested transaction sequence number as it's stored on Ledger.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_pool_config_request(self, submitter_did: str, writes: bool, force: bool) -> dict:
        """
        Builds a POOL_CONFIG request. Request to change Pool's configuration.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param writes: Whether any write requests can be processed by the pool
                       (if false, then pool goes to read-only state). True by default.
        :param force: Whether we should apply transaction (for example, move pool to read-only state)
                      without waiting for consensus of this transaction
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_pool_restart_request(self, submitter_did: str, action: str, datetime: str) -> dict:
        """
        Builds a POOL_RESTART request

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param action       : Action that pool has to do after received transaction.
                              Can be "start" or "cancel"
        :param datetime           : Time when pool must be restarted.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_pool_upgrade_request(self,
            submitter_did: str, name: str, version: str, action: str, _sha256: str, _timeout: Optional[int],
            schedule: Optional[str], justification: Optional[str], reinstall: bool, force: bool, package: Optional[str]
    ) -> dict:
        """
        Builds a POOL_UPGRADE request. Request to upgrade the Pool (sent by Trustee).
        It upgrades the specified Nodes (either all nodes in the Pool, or some specific ones).

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param name: Human-readable name for the upgrade.
        :param version: The version of indy-node package we perform upgrade to.
                        Must be greater than existing one (or equal if reinstall flag is True).
        :param action: Either start or cancel.
        :param _sha256: sha256 hash of the package.
        :param _timeout: (Optional) Limits upgrade time on each Node.
        :param schedule: (Optional) Schedule of when to perform upgrade on each node. Map Node DIDs to upgrade time.
        :param justification: (Optional) justification string for this particular Upgrade.
        :param reinstall: Whether it's allowed to re-install the same version. False by default.
        :param force: Whether we should apply transaction (schedule Upgrade) without waiting
                      for consensus of this transaction.
        :param package: (Optional) Package to be upgraded.
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_revoc_reg_def_request(self, submitter_did: str, data: str) -> dict:
        """
        Builds a REVOC_REG_DEF request. Request to add the definition of revocation registry
        to an exists credential definition.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: Revocation Registry data:
          {
              "id": string - ID of the Revocation Registry,
              "revocDefType": string - Revocation Registry type (only CL_ACCUM is supported for now),
              "tag": string - Unique descriptive ID of the Registry,
              "credDefId": string - ID of the corresponding CredentialDefinition,
              "value": Registry-specific data {
                  "issuanceType": string - Type of Issuance(ISSUANCE_BY_DEFAULT or ISSUANCE_ON_DEMAND),
                  "maxCredNum": number - Maximum number of credentials the Registry can serve.
                  "tailsHash": string - Hash of tails.
                  "tailsLocation": string - Location of tails file.
                  "publicKeys": <public_keys> - Registry's public key.
              },
              "ver": string - version of revocation registry definition json.
          }

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_revoc_reg_def_request(self, submitter_did: Optional[str], rev_reg_def_id: str) -> dict:
        """
        Builds a GET_REVOC_REG_DEF request. Request to get a revocation registry definition,
        that Issuer creates for a particular Credential Definition.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param rev_reg_def_id: ID of Revocation Registry Definition in ledger.

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_revoc_reg_def_response(self, get_revoc_ref_def_response: dict) -> (str, dict):
        """
        Parse a GET_REVOC_REG_DEF response to get Revocation Registry Definition in the format compatible with Anoncreds API.

        :param get_revoc_ref_def_response: response of GET_REVOC_REG_DEF request.
        :return: Revocation Registry Definition Id and Revocation Registry Definition json.
          {
              "id": string - ID of the Revocation Registry,
              "revocDefType": string - Revocation Registry type (only CL_ACCUM is supported for now),
              "tag": string - Unique descriptive ID of the Registry,
              "credDefId": string - ID of the corresponding CredentialDefinition,
              "value": Registry-specific data {
                  "issuanceType": string - Type of Issuance(ISSUANCE_BY_DEFAULT or ISSUANCE_ON_DEMAND),
                  "maxCredNum": number - Maximum number of credentials the Registry can serve.
                  "tailsHash": string - Hash of tails.
                  "tailsLocation": string - Location of tails file.
                  "publicKeys": <public_keys> - Registry's public key.
              },
              "ver": string - version of revocation registry definition json.
          }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_revoc_reg_entry_request(self,
            submitter_did: str, revoc_reg_def_id: str, rev_def_type: str, value: dict
    ) -> dict:
        """
        Builds a REVOC_REG_ENTRY request.  Request to add the RevocReg entry containing
        the new accumulator value and issued/revoked indices.
        This is just a delta of indices, not the whole list. So, it can be sent each time a new credential is issued/revoked.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param revoc_reg_def_id:  ID of the corresponding RevocRegDef.
        :param rev_def_type:  Revocation Registry type (only CL_ACCUM is supported for now).
        :param value: Registry-specific data:
           {
               value: {
                   prevAccum: string - previous accumulator value.
                   accum: string - current accumulator value.
                   issued: array<number> - an array of issued indices.
                   revoked: array<number> an array of revoked indices.
               },
               ver: string - version revocation registry entry json

           }
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_revoc_reg_request(self,
            submitter_did: Optional[str], revoc_reg_def_id: str, timestamp: int
    ) -> dict:
        """
        Builds a GET_REVOC_REG request. Request to get the accumulated state of the Revocation Registry
        by ID. The state is defined by the given timestamp.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param revoc_reg_def_id:  ID of the corresponding Revocation Registry Definition in ledger.
        :param timestamp: Requested time represented as a total number of seconds from Unix Epoch
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_revoc_reg_response(self, get_revoc_reg_response: dict) -> (str, dict, int):
        """
        Parse a GET_REVOC_REG response to get Revocation Registry in the format compatible with Anoncreds API.

        :param get_revoc_reg_response: response of GET_REVOC_REG request.
        :return: Revocation Registry Definition Id, Revocation Registry json and Timestamp.
          {
              "value": Registry-specific data {
                  "accum": string - current accumulator value.
              },
              "ver": string - version revocation registry json
          }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_revoc_reg_delta_request(self,
            submitter_did: Optional[str], revoc_reg_def_id: str, from_: Optional[int], to: int
    ) -> dict:
        """
        Builds a GET_REVOC_REG_DELTA request. Request to get the delta of the accumulated state of the Revocation Registry.
        The Delta is defined by from and to timestamp fields.
        If from is not specified, then the whole state till to will be returned.

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param revoc_reg_def_id:  ID of the corresponding Revocation Registry Definition in ledger.
        :param from_: Requested time represented as a total number of seconds from Unix Epoch
        :param to: Requested time represented as a total number of seconds from Unix Epoch
        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def parse_get_revoc_reg_delta_response(self, get_revoc_reg_delta_response: dict) -> (str, dict, int):
        """
        Parse a GET_REVOC_REG_DELTA response to get Revocation Registry Delta in the format compatible with Anoncreds API.

        :param get_revoc_reg_delta_response: response of GET_REVOC_REG_DELTA request.
        :return: Revocation Registry Definition Id, Revocation Registry Delta json and Timestamp.
          {
              "value": Registry-specific data {
                  prevAccum: string - previous accumulator value.
                  accum: string - current accumulator value.
                  issued: array<number> - an array of issued indices.
                  revoked: array<number> an array of revoked indices.
              },
              "ver": string
          }
        """
        raise NotImplemented()

    @abstractmethod
    async def get_response_metadata(self, response: dict) -> dict:
        """
         Parse transaction response to fetch metadata.
         The important use case for this method is validation of Node's response freshens.

         Distributed Ledgers can reply with outdated information for consequence read request after write.
         To reduce pool load libindy sends read requests to one random node in the pool.
         Consensus validation is performed based on validation of nodes multi signature for current ledger Merkle Trie root.
         This multi signature contains information about the latest ldeger's transaction ordering time and sequence number that this method returns.

         If node that returned response for some reason is out of consensus and has outdated ledger
         it can be caught by analysis of the returned latest ledger's transaction ordering time and sequence number.

         There are two ways to filter outdated responses:
             1) based on "seqNo" - sender knows the sequence number of transaction that he consider as a fresh enough.
             2) based on "txnTime" - sender knows the timestamp that he consider as a fresh enough.

         Note: response of GET_VALIDATOR_INFO request isn't supported

        :param response: response of write or get request.
        :return: Response Metadata.
        {
            "seqNo": Option<u64> - transaction sequence number,
            "txnTime": Option<u64> - transaction ordering time,
            "lastSeqNo": Option<u64> - the latest transaction seqNo for particular Node,
            "lastTxnTime": Option<u64> - the latest transaction ordering time for particular Node
        }
        """
        raise NotImplemented()

    @abstractmethod
    async def build_auth_rule_request(self,
            submitter_did: str, txn_type: str, action: str, field: str, old_value: Optional[str],
            new_value: Optional[str], constraint: dict
    ) -> dict:
        """
        Builds a AUTH_RULE request. Request to change authentication rules for a ledger transaction.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param txn_type: ledger transaction alias or associated value.
        :param action: type of an action.
           Can be either "ADD" (to add a new rule) or "EDIT" (to edit an existing one).
        :param field: transaction field.
        :param old_value: (Optional) old value of a field, which can be changed to a new_value (mandatory for EDIT action).
        :param new_value: (Optional) new value that can be used to fill the field.
        :param constraint: set of constraints required for execution of an action in the following format:
            {
                constraint_id - <string> type of a constraint.
                    Can be either "ROLE" to specify final constraint or  "AND"/"OR" to combine constraints.
                role - <string> (optional) role of a user which satisfy to constrain.
                sig_count - <u32> the number of signatures required to execution action.
                need_to_be_owner - <bool> (optional) if user must be an owner of transaction (false by default).
                off_ledger_signature - <bool> (optional) allow signature of unknow for ledger did (false by default).
                metadata - <object> (optional) additional parameters of the constraint.
            }
          can be combined by
            {
                'constraint_id': <"AND" or "OR">
                'auth_constraints': [<constraint_1>, <constraint_2>]
            }

        Default ledger auth rules: https://github.com/hyperledger/indy-node/blob/master/docs/source/auth_rules.md

        More about AUTH_RULE request: https://github.com/hyperledger/indy-node/blob/master/docs/source/requests.md#auth_rule

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_auth_rules_request(self, submitter_did: str, data: dict) -> dict:
        """
        Builds a AUTH_RULES request. Request to change multiple authentication rules for a ledger transaction.

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param data: a list of auth rules: [
            {
                "auth_type": ledger transaction alias or associated value,
                "auth_action": type of an action,
                "field": transaction field,
                "old_value": (Optional) old value of a field, which can be changed to a new_value (mandatory for EDIT action),
                "new_value": (Optional) new value that can be used to fill the field,
                "constraint": set of constraints required for execution of an action in the format described above for `build_auth_rule_request` function.
            }
        ]

        Default ledger auth rules: https://github.com/hyperledger/indy-node/blob/master/docs/source/auth_rules.md

        More about AUTH_RULE request: https://github.com/hyperledger/indy-node/blob/master/docs/source/requests.md#auth_rules

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_auth_rule_request(self,
            submitter_did: Optional[str], txn_type: Optional[str], action: Optional[str], field: Optional[str],
            old_value: Optional[str], new_value: Optional[str]
    ) -> dict:
        """
        Builds a GET_AUTH_RULE request. Request to get authentication rules for a ledger transaction.

        NOTE: Either none or all transaction related parameters must be specified (`old_value` can be skipped for `ADD` action).
            * none - to get all authentication rules for all ledger transactions
            * all - to get authentication rules for specific action (`old_value` can be skipped for `ADD` action)

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param txn_type: target ledger transaction alias or associated value.
        :param action: target action type. Can be either "ADD" or "EDIT".
        :param field: target transaction field.
        :param old_value: (Optional) old value of field, which can be changed to a new_value (must be specified for EDIT action).
        :param new_value: (Optional) new value that can be used to fill the field.

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_txn_author_agreement_request(self,
            submitter_did: str, text: Optional[str], version: str,
            ratification_ts: Optional[int] = None, retirement_ts: Optional[int] = None
    ) -> dict:
        """
        Builds a TXN_AUTHR_AGRMT request. Request to add a new version of Transaction Author Agreement to the ledger.

        EXPERIMENTAL

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param text: (Optional) a content of the TTA.
                              Mandatory in case of adding a new TAA. An existing TAA text can not be changed.
                              for Indy Node version <= 1.12.0:
                                  Use empty string to reset TAA on the ledger
                              for Indy Node version > 1.12.0
                                  Should be omitted in case of updating an existing TAA (setting `retirement_ts`)
        :param version: a version of the TTA (unique UTF-8 string).
        :param ratification_ts: Optional) the date (timestamp) of TAA ratification by network government.
                              for Indy Node version <= 1.12.0:
                                 Must be omitted
                              for Indy Node version > 1.12.0:
                                 Must be specified in case of adding a new TAA
                                 Can be omitted in case of updating an existing TAA
        :param retirement_ts: (Optional) the date (timestamp) of TAA retirement.
                              for Indy Node version <= 1.12.0:
                                  Must be omitted
                              for Indy Node version > 1.12.0:
                                  Must be omitted in case of adding a new (latest) TAA.
                                  Should be used for updating (deactivating) non-latest TAA on the ledger.

        Note: Use `build_disable_all_txn_author_agreements_request` to disable all TAA's on the ledger.

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_disable_all_txn_author_agreements_request(self, submitter_did: str) -> dict:
        """
        Builds a DISABLE_ALL_TXN_AUTHR_AGRMTS request. Request to disable all Transaction Author Agreement on the ledger.

        EXPERIMENTAL

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_txn_author_agreement_request(self, submitter_did: Optional[str], data: dict=None) -> dict:
        """
        Builds a GET_TXN_AUTHR_AGRMT request. Request to get a specific Transaction Author Agreement from the ledger.

        EXPERIMENTAL

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param data: (Optional) specifies a condition for getting specific TAA.
         Contains 3 mutually exclusive optional fields:
         {
             hash: Optional<str> - hash of requested TAA,
             version: Optional<str> - version of requested TAA.
             timestamp: Optional<i64> - ledger will return TAA valid at requested timestamp.
         }
         Null data or empty JSON are acceptable here. In this case, ledger will return the latest version of TAA.

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_acceptance_mechanisms_request(self,
            submitter_did: str, aml: dict, version: str, aml_context: Optional[str]
    ) -> dict:
        """
        Builds a SET_TXN_AUTHR_AGRMT_AML request. Request to add a new list of acceptance mechanisms for transaction author agreement.
        Acceptance Mechanism is a description of the ways how the user may accept a transaction author agreement.

        EXPERIMENTAL

        :param submitter_did: Identifier (DID) of the transaction author as base58-encoded string.
                              Actual request sender may differ if Endorser is used (look at `append_request_endorser`)
        :param aml: a set of new acceptance mechanisms:
        {
            “<acceptance mechanism label 1>”: { acceptance mechanism description 1},
            “<acceptance mechanism label 2>”: { acceptance mechanism description 2},
            ...
        }
        :param version: a version of new acceptance mechanisms. (Note: unique on the Ledger)
        :param aml_context: (Optional) common context information about acceptance mechanisms (may be a URL to external resource).

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def build_get_acceptance_mechanisms_request(self,
            submitter_did: Optional[str], timestamp: Optional[int], version: Optional[str]
    ) -> dict:
        """
        Builds a GET_TXN_AUTHR_AGRMT_AML request. Request to get a list of  acceptance mechanisms from the ledger
        valid for specified time or the latest one.

        EXPERIMENTAL

        :param submitter_did: (Optional) DID of the read request sender (if not provided then default Libindy DID will be used).
        :param timestamp: (Optional) time to get an active acceptance mechanisms. The latest one will be returned for the empty timestamp.
        :param version: (Optional) version of acceptance mechanisms.

        NOTE: timestamp and version cannot be specified together.

        :return: Request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def append_txn_author_agreement_acceptance_to_request(self,
            request: dict, text: Optional[str], version: Optional[str],
            taa_digest: Optional[str], mechanism: str, time: int
    ) -> dict:
        """
        Append transaction author agreement acceptance data to a request.
        This function should be called before signing and sending a request
        if there is any transaction author agreement set on the Ledger.

        EXPERIMENTAL

        This function may calculate hash by itself or consume it as a parameter.
        If all text, version and taa_digest parameters are specified, a check integrity of them will be done.

        :param request: original request data json.
        :param text and version: (Optional) raw data about TAA from ledger.
                   These parameters should be passed together.
                   These parameters are required if taa_digest parameter is omitted.
        :param taa_digest: (Optional) digest on text and version.
                          Digest is sha256 hash calculated on concatenated strings: version || text.
                          This parameter is required if text and version parameters are omitted.
        :param mechanism: mechanism how user has accepted the TAA
        :param time: UTC timestamp when user has accepted the TAA. Note that the time portion will be discarded to avoid a privacy risk.

        :return: Updated request result as json.
        """
        raise NotImplemented()

    @abstractmethod
    async def append_request_endorser(self, request: dict, endorser_did: str) -> dict:
        """
        Append Endorser to an existing request.

        An author of request still is a `DID` used as a `submitter_did` parameter for the building of the request.
        But it is expecting that the transaction will be sent by the specified Endorser.

        Note: Both Transaction Author and Endorser must sign output request after that.

        More about Transaction Endorser: https://github.com/hyperledger/indy-node/blob/master/design/transaction_endorser.md
                                         https://github.com/hyperledger/indy-sdk/blob/master/docs/configuration.md

        :param request: original request data json.
        :param endorser_did: DID of the Endorser that will submit the transaction.
                             The Endorser's DID must be present on the ledger.

        :return: Updated request result as json.
        """
        raise NotImplemented()
