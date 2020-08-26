from sirius_sdk.messaging import check_for_attributes


class DIDDoc(dict):
    DID = 'did'
    DID_DOC = 'did_doc'
    VCX_DID = 'DID'
    VCX_DID_DOC = 'DIDDoc'

    def validate(self):
        check_for_attributes(
            self,
            [
                '@context',
                'publicKey',
                'service'
            ]
        )

        for publicKeyBlock in self['publicKey']:
            check_for_attributes(
                publicKeyBlock,
                [
                    'id',
                    'type',
                    'controller',
                    'publicKeyBase58'
                ]
            )

        for serviceBlock in self['service']:
            check_for_attributes(
                serviceBlock,
                [
                    ('type', 'IndyAgent'),
                    'recipientKeys',
                    'serviceEndpoint'
                ]
            )

    def extract_service(self, high_priority: bool = True, type_: str = 'IndyAgent'):
        services = self.get("service", [])
        if services:
            ret = None
            for service in services:
                if service['type'] != type_:
                    continue
                if ret is None:
                    ret = service
                else:
                    if high_priority:
                        if service.get("priority", 0) > ret.get("priority", 0):
                            ret = service
            return ret
        else:
            return None
