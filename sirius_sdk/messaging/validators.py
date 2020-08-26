from sirius_sdk.errors.exceptions import SiriusValidationError
from sirius_sdk.messaging.message import Message
from sirius_sdk.messaging.fields import *


ID = '@id'
TYPE = '@type'
THREAD_DECORATOR = '~thread'
THREAD_ID = 'thid'
PARENT_THREAD_ID = 'pthid'
SENDER_ORDER = 'sender_order'
RECEIVED_ORDERS = 'received_orders'
THREADING_ERROR = 'threading_error'
TIMING_ERROR = 'timing_error'

TIMING_DECORATOR = '~timing'
IN_TIME = 'in_time'
OUT_TIME = 'out_time'
STALE_TIME = 'stale_time'
EXPIRES_TIME = 'expires_time'
DELAY_MILLI = 'delay_milli'
WAIT_UNTIL_TIME = 'wait_until_time'


def check_for_attributes(partial: dict, expected_attributes: Iterable):
    for attribute in expected_attributes:
        if isinstance(attribute, tuple):
            if attribute[0] not in partial:
                raise SiriusValidationError('Attribute "{}" is missing from message: \n{}'.format(attribute[0], partial))
            if partial[attribute[0]] != attribute[1]:
                raise SiriusValidationError('Message.{}: {} != {}'.format(attribute[0], partial[attribute[0]], attribute[1]))
        else:
            if attribute not in partial:
                raise SiriusValidationError('Attribute "{}" is missing from message: \n{}'.format(attribute, partial))


def validate_common_blocks(partial: dict):
    """Validate blocks of message like threading, timing, etc
    """
    _validate_thread_block(partial)
    _validate_timing_block(partial)


def _validate_thread_block(partial: dict):
    if THREAD_DECORATOR in partial:
        thread = partial[THREAD_DECORATOR]
        check_for_attributes(thread, [THREAD_ID])

        thread_id = thread[THREAD_ID]
        if partial.get(ID) and thread_id == partial[ID]:
            raise SiriusValidationError('Thread id {} cannot be equal to outer id {}'.format(thread_id, partial[ID]))
        if thread.get(PARENT_THREAD_ID) and thread[PARENT_THREAD_ID] in (thread_id, partial[ID]):
            raise SiriusValidationError('Parent thread id {} must be different than thread id and outer id'.format(
                thread[PARENT_THREAD_ID]))

        if thread.get(SENDER_ORDER):
            non_neg_num = NonNegativeNumberField()
            err = non_neg_num.validate(thread[SENDER_ORDER])
            if not err:
                if RECEIVED_ORDERS in thread and thread[RECEIVED_ORDERS]:
                    recv_ords = thread[RECEIVED_ORDERS]
                    err = MapField(DIDField(), non_neg_num).validate(recv_ords)
            if err:
                raise ValueError(err)


def _validate_timing_block(partial: dict):
    if TIMING_DECORATOR in partial:
        timing = partial[TIMING_DECORATOR]
        non_neg_num = NonNegativeNumberField()
        iso_data = ISODatetimeStringField()
        expected_iso_fields = [IN_TIME, OUT_TIME, STALE_TIME, EXPIRES_TIME, WAIT_UNTIL_TIME]
        for f in expected_iso_fields:
            if f in timing:
                err = iso_data.validate(timing[f])
                if err:
                    raise SiriusValidationError(err)
        if DELAY_MILLI in timing:
            err = non_neg_num.validate(timing[DELAY_MILLI])
            if err:
                raise SiriusValidationError(err)

        # In time cannot be greater than out time
        if IN_TIME in timing and OUT_TIME in timing:
            t_in = iso_data.parse_func(timing[IN_TIME])
            t_out = iso_data.parse_func(timing[OUT_TIME])

            if t_in > t_out:
                raise SiriusValidationError('{} cannot be greater than {}'.format(IN_TIME, OUT_TIME))

        # Stale time cannot be greater than expires time
        if STALE_TIME in timing and EXPIRES_TIME in timing:
            t_stale = iso_data.parse_func(timing[STALE_TIME])
            t_exp = iso_data.parse_func(timing[EXPIRES_TIME])

            if t_stale > t_exp:
                raise SiriusValidationError('{} cannot be greater than {}'.format(STALE_TIME, EXPIRES_TIME))
