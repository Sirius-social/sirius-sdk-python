import contextlib
from typing import Union, List, Dict

import sirius_sdk
from sirius_sdk.abstract.p2p import Pairwise


@contextlib.asynccontextmanager
async def as_caller(
        called: Pairwise, thid: str, cast: Union[List, Dict], pthid: str = None, co_binding_id: str = None,
        time_to_live: int = None, logger=None, *args, **kwargs
):
    """Invoke co-protocol as Caller
        see details:
          - Feature: https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
          - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols

    Sample code:
        async with as_caller(p2p, thid='payment-thread-id', cast=[{'role': 'payer', 'id': 'did:peer:abc123' }]) as payment_protocol:
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

    :param called: (required) is the called entity getting input and giving output
    :param thid: (required) protocol thread-id
    :param cast: (required) init binding data
    :param co_binding_id: (optional) extended binding id
    :param pthid: (optional) parent protocol thread-id
    :param time_to_live: (optional) max time protocol will be alive: will be automatically detached when timeout occured
    :param logger: (optional) self-designed logger
    """

    protocol = sirius_sdk.aries_rfc.Caller(
        called=called, thid=thid, pthid=pthid, time_to_live=time_to_live, logger=logger, *args, **kwargs
    )
    success, ctx = await protocol.bind(cast=cast, co_binding_id=co_binding_id)
    if not success:
        if protocol.problem_report:
            raise RuntimeError(f'Error while binding co-protocol: "{protocol.problem_report.explain}"')
        else:
            raise RuntimeError(f'Error while binding co-protocol')
    try:
        yield protocol
    finally:
        await protocol.detach()


@contextlib.asynccontextmanager
async def as_called(caller: Pairwise, request: sirius_sdk.aries_rfc.CoProtocolBind, logger=None, *args, **kwargs):
    """Invoke co-protocol as Called entity
        see details:
          - Feature: https://github.com/hyperledger/aries-rfcs/tree/main/features/0482-coprotocol-protocol
          - Concept: https://github.com/hyperledger/aries-rfcs/blob/main/concepts/0478-coprotocols

        Sample code:
            async with as_called(p2p, request) as payment_protocol:
                # declare what currencies we supports
                await payment_protocol.attach(currencies=['USDT', 'ETH', 'BTC'])
                success, data, extra = await payment_protocol.wait_input()
                if success:
                    # Make some steps to process payment
                    .....
                    await payment_protocol.output(data={'success': True, 'report': '...'})
                else:
                    # print problem_report
                    if payment_protocol.problem_report:
                        print('Error: ' + payment_protocol.problem_report.explain)

        :param caller: (required) is the called entity getting input and giving output
        :param request: (required) caller bind request message
        :param logger: (optional) self-designed logger
    """
    protocol = await sirius_sdk.aries_rfc.Called.open(caller=caller, request=request, logger=logger, *args, **kwargs)
    try:
        yield protocol
    finally:
        await protocol.done()
