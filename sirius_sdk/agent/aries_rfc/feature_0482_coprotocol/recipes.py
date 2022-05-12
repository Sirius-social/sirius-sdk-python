import contextlib
from typing import Union, List, Dict

from sirius_sdk import Pairwise
from .state_machines import Caller


@contextlib.asynccontextmanager
async def invoke(
        called: Pairwise, thid: str, cast: Union[List, Dict], pthid: str = None, co_binding_id: str = None,
        time_to_live: int = None, logger=None, *args, **kwargs
):
    """Invoke co-protocol
        see details:
          - Feature: https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
          - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols

    Sample code:
        async with invoke(called=p2p, thid='payment-thread-id', cast=[{'role': 'payer', 'id': 'did:peer:abc123' }]) as payment_protocol:
            # check if payment protocol supports out currencies
            if "USDT" in payment_protocol.context['currencies]:
                await protocol.input(data=[{"amount": 10, "currency": "USDT"}])
                success, data, extra = await payment_protocol.wait_output()
                if success is True:
                    print('Payment was successfully terminated')

                    # Go to next steps
                    .....
                else:
                    print('Error: ' + payment_protocol.problem_report.explain)
            else:
                await payment_protocol.raise_problem(problem_code='-1', explain='Unsupported currency')
                await payment_protocol.detach()

    :param called: (required) is the entity getting input and giving output
    :param thid: (required) protocol thread-id
    :param cast: (required)
    :param co_binding_id:
    :param pthid:
    :param time_to_live:
    :param logger:
    :return:
    """

    protocol = Caller(called=called, thid=thid, pthid=pthid, time_to_live=time_to_live, logger=logger, *args, **kwargs)
    success, ctx = await protocol.bind(cast=cast, co_binding_id=co_binding_id)
    if not success:
        if protocol.problem_report:
            raise RuntimeError(f'Error while binding co-protocol: "{protocol.problem_report.explain}"')
        else:
            raise RuntimeError(f'Error while binding co-protocol')
    try:
        yield protocol
    finally:
        await protocol.done()
