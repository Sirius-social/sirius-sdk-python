class Pairwise:

    class Their:

        def __init__(self, did, label, endpoint, verkey, routing_keys=None):
            self.did = did
            self.label = label
            self.endpoint = endpoint
            self.verkey = verkey
            self.routing_keys = routing_keys

    class Me:

        def __init__(self, did, verkey):
            self.did = did
            self.verkey = verkey

    def __init__(self, meta: dict=None):
        self.__their = None
        self.__me = None

    @property
    def their(self) -> Their:
        return self.__their

    @property
    def me(self) -> Me:
        return self.__me
