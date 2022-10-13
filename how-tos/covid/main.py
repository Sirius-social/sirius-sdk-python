import asyncio
import datetime
import uuid
from typing import List, Dict
from helpers import *

import sirius_sdk
from sirius_sdk.agent.consensus.simple import MicroLedgerSimpleConsensus, ProposeTransactionsMessage, \
    InitRequestLedgerMessage
from sirius_sdk.agent.microledgers.abstract import Transaction
from sirius_sdk.base import AbstractStateMachine
from sirius_sdk.abstract.listener import Event


class Logger:

    async def __call__(self, *args, **kwargs):
        print(dict(**kwargs))

# параметры соединения с агентом ковид лаборатории
LABORATORY = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': 'BXXwMmUlw7MTtVWhcVvbSVWbC1GopGXDuo+oY3jHkP/4jN3eTlPDwSwJATJbzwuPAAaULe6HFEP5V57H6HWNqYL4YtzWCkW2w+H7fLgrfTLaBtnD7/P6c5TDbBvGucOV'.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('EzJKT2Q6Cw8pwy34xPa9m2qPCSvrMmCutaq1pPGBQNCn', '273BEpAM8chzfMBDSZXKhRMPPoaPRWRDtdMmNoKLmJUU6jvm8Nu8caa7dEdcsvKpCTHmipieSsatR4aMb1E8hQAa'),
            their_verkey='342Bm3Eq9ruYfvHVtLxiBLLFj54Tq6p8Msggt7HiWxBt'
        )
    },
    'alias': 'Laboratory',
    'did': 'X1YdguoHBaY1udFQMbbKKG',  # публичный (т.е. записанный в публичный распределенный реестр) децентрализованный идентификатор ковид лаборатории
    'verkey': 'HMf57wiWK1FhtzLbm76o37tEMJvaCbWfGsaUzCZVZwnT',  # соответствующий данному DID публичный ключ
    'endpoint': 'https://demo.socialsirius.com/endpoint/b14bc782806c4c298b56e38d79fb51e9'  # адрес агента лаборатории
}

# параметры соединения с агентом авиакомпании
AIR_COMPANY = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': '/MYok4BSllG8scfwXVVRK8V47I1PC44mktwiJKKduf38Yb7UgIsq8n4SXVBrRwIzHMQA/6sdiKgrB20Kbw9ieHbOGlxx3UVlWNM0Xfc9Rgk85cCLSHWM2vqlNQSGwHAM+udXpuPwAkfKjiUtzyPBcA=='.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('BhDMxfvhc2PZ4BpGTExyWHYkJDFPhmXpaRvUoCoNJ8rL', '2wwakvFwBRWbFeLyDbsH6cYVve6FBH6DL133sPNN87jWYbc6rHXj7Q3dnAsbB6EuNwquucsDzSBhNcpxgyVLCCYg'),
            their_verkey='8VNHw79eMTZJBasgjzdwyKyCYA88ajm9gvP98KGcjaBt'
        )
    },
    'alias': 'AirCompany',
    'did': 'XwVCkzM6sMxk87M2GKtya6',  # публичный (т.е. записанный в публичный распределенный реестр) децентрализованный идентификатор авиакомпании
    'verkey': 'Hs4FPfB1d7nFUcqbMZqofFg4qoeGxGThmSbunJYpVAM6',  # соответствующий данному DID публичный ключ
    'endpoint': 'https://demo.socialsirius.com/endpoint/7d4b74435ca34efeb600537cde08186d'  # адрес агента авиакомпании
}

# параметры соединения с агентом аэропорта
AIRPORT = {
    'sdk': {
        'server_uri': 'https://demo.socialsirius.com',
        'credentials': '/MYok4BSllG8scfwXVVRK3NATRRtESRnhUHOU3nJxxZ+gg81/srwEPNWfZ+3+6GaEHcqghOJvRoV7taA/vCd2+q2hIEpDO/yCPfMr4x2K0vC/pom1gFRJwJAKI3LpMy3'.encode(),
        'p2p': sirius_sdk.P2PConnection(
            my_keys=('HBEe9KkPCK4D1zs6UBzLqWp6j2Gj88zy3miqybvYx42p', '23jutNJBbgn8bbX53Qr36JSeS2VtZHvY4DMqazXHq6mDEPNkuA3FkKVGAMJdjPznfizLg9nh448DXZ7e1724qk1a'),
            their_verkey='BNxpmTgs9B3yMURa1ta7avKuBA5wcBp5ZmXfqPFPYGAP'
        )
    },
    'alias': 'Airport',
    'did': 'Ap29nQ3Kf2bGJdWEV3m4AG',  # публичный (т.е. записанный в публичный распределенный реестр) децентрализованный идентификатор аэропорта
    'verkey': '6M8qgMdkqGzQ2yhryV3F9Kvk785qAFny5JuLp1CJCcHW',  # соответствующий данному DID публичный ключ
    'endpoint': 'https://demo.socialsirius.com/endpoint/68bec29ce63240bc9981f0d8759ec5f2'  # адрес агента аэропорта
}

# имя публичного распределенного реестра
DKMS_NAME = 'test_network'

# имя децентрализованного миктореестра, созданного между лабораторией, авиакомпанией и аэропортом для хранения положительных ковид тестов
COVID_MICROLEDGER_NAME = "covid_ledger_test3"


class Laboratory:

    def __init__(self, hub_credentials: dict, pairwises: List[sirius_sdk.Pairwise], me: sirius_sdk.Pairwise.Me):
        self.hub_credentials: dict = hub_credentials
        self.pairwises: List[sirius_sdk.Pairwise] = pairwises
        self.me: sirius_sdk.Pairwise.Me = me
        self.covid_microledger_participants = [me.did] + [pw.their.did for pw in pairwises]

    async def listen(self):
        async with sirius_sdk.context(**self.hub_credentials): # работаем в контексте лабы (все вызовы выполняются от имени агента лабы)
            await self.init_microledger()
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if isinstance(event.message, ProposeTransactionsMessage): # получен запрос на добавление транзакции в микрореестр положительных ковид справок
                    machine = MicroLedgerSimpleConsensus(self.me)
                    await machine.accept_commit(event.pairwise, event.message)

    async def init_microledger(self):
        # лаборатория выступает инициатором создания микрореестра положительных ковид справок
        if not await sirius_sdk.Microledgers.is_exists(COVID_MICROLEDGER_NAME):
            print("Initializing microledger consensus")
            machine = MicroLedgerSimpleConsensus(self.me)
            ok, _ = await machine.init_microledger(COVID_MICROLEDGER_NAME, self.covid_microledger_participants, [])
            if ok:
                print("Consensus successfully initialized")
            else:
                print("Consensus initialization failed!")

    async def issue_test_results(self, cred_def: sirius_sdk.CredentialDefinition, schema: sirius_sdk.Schema, test_results: dict):
        async with sirius_sdk.context(**self.hub_credentials): # работаем от имени агента лабы
            connection_key = await sirius_sdk.Crypto.create_key() # создаем случайный уникальный ключ соединения между агентом лабы и сириус коммуникатором пользователя
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]  # точка подключения к агенту лабы (интернет адрес)
            invitation = sirius_sdk.aries_rfc.Invitation(  # Создаем приглашение пользователю подключиться к лабе
                label="Invitation to connect with medical organization",
                recipient_keys=[connection_key],
                endpoint=simple_endpoint.address
            )

            qr_content = invitation.invitation_url
            qr_url = await sirius_sdk.generate_qr_code(qr_content) # агент лабы генерирует уникальный qr код для ранее созданного приглашения

            # пользователь сканирует qr код при помощи sirius коммуникатора. Коммуникатор отправляет агенту лабы запрос на подключение
            print("Scan this QR by Sirius App for receiving the Covid test result " + qr_url)

            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if event.recipient_verkey == connection_key and isinstance(event.message, sirius_sdk.aries_rfc.ConnRequest):
                    #  агент лабы получает запрос от пользователя на подключение (запрос соответствкет ранее сгенерированному уникальному ключу соединения)
                    request: sirius_sdk.aries_rfc.ConnRequest = event.message
                    #  агент лабы создает уникальный децентрализованный идентификатор (did) для связи с пользователем (который тоже создает уникальный did для этого соединения)
                    my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
                    sm = sirius_sdk.aries_rfc.Inviter(
                        me=sirius_sdk.Pairwise.Me(
                            did=my_did,
                            verkey=my_verkey
                        ),
                        connection_key=connection_key,
                        my_endpoint=simple_endpoint
                    )
                    # Запускается процесс установки соединения в соответствии с открытым протоколом Aries 0160
                    success, p2p = await sm.create_connection(request)
                    if success:
                        # соединение успешно установлено, о чем сообщается пользователю путем отправки простого текстового сообщения на его сириус коммуникатор
                        message = sirius_sdk.aries_rfc.Message(
                            content="Welcome to the covid laboratory!",
                            locale="en"
                        )
                        print(message)
                        await sirius_sdk.send_to(message, p2p)

                        issuer = sirius_sdk.aries_rfc.Issuer(p2p)
                        preview = [sirius_sdk.aries_rfc.ProposedAttrib(key, str(value)) for key, value in test_results.items()]
                        translation = [
                            sirius_sdk.aries_rfc.AttribTranslation("full_name", "Patient Full Name"),
                            sirius_sdk.aries_rfc.AttribTranslation("location", "Patient location"),
                            sirius_sdk.aries_rfc.AttribTranslation("bio_location", "Biomaterial sampling point"),
                            sirius_sdk.aries_rfc.AttribTranslation("timestamp", "Timestamp"),
                            sirius_sdk.aries_rfc.AttribTranslation("approved", "Laboratory specialist"),
                            sirius_sdk.aries_rfc.AttribTranslation("has_covid", "Covid test result")
                        ]

                        # лаборатория выдает результаты теста на ковид пользователю.
                        # Результаты оформлены в соответствии с ранее зареестрированной схемой и подписаны ЦП лаборатории.
                        # Пользователь сохраняет полученные результаты на своем сириус коммуникаторе
                        ok = await issuer.issue(
                            values=test_results,
                            schema=schema,
                            cred_def=cred_def,
                            preview=preview,
                            translation=translation,
                            comment="Here is your covid test results",
                            locale="en"
                        )
                        if ok:
                            print("Covid test confirmation was successfully issued")
                            # если результат теста оказался положительным, он записывается в соответствующий распределенный микрореестр,
                            # достут к которому имеет лаборатория, авиакомпания и аэропорт
                            if test_results["has_covid"]:
                                ledger = await sirius_sdk.Microledgers.ledger(COVID_MICROLEDGER_NAME)
                                machine = MicroLedgerSimpleConsensus(self.me, logger=Logger())
                                tr = Transaction({
                                    "test_res": test_results
                                })
                                await machine.commit(ledger, self.covid_microledger_participants, [tr])

                    break


async def create_med_creds(issuer_did: str) -> (sirius_sdk.CredentialDefinition, sirius_sdk.Schema):
    schema_name = "Covid test result 2"
    # создаем схему (форму) для теста на ковид с полями "approved", "timestamp", "bio_location" и т д
    schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(issuer_did, schema_name, '1.0',
                                         ["approved", "timestamp", "bio_location", "location", "full_name", "has_covid"])
    l = await sirius_sdk.ledger(DKMS_NAME)
    # если схемы ковид теста нет в распределенном реестре, то ее нужно туда записать, чтобы другие участики могли ей воспользоваться
    schema = await l.ensure_schema_exists(anon_schema, issuer_did)
    if not schema:
        ok, schema = await l.register_schema(anon_schema, issuer_did)
        if ok:
            print("Covid test result registered successfully")
        else:
            print("Covid test result was not registered")
            return None, None

    else:
        print("Med schema is exists in the ledger")

    ok, cred_def = await l.register_cred_def(
        cred_def=sirius_sdk.CredentialDefinition(tag='TAG', schema=schema),
        submitter_did=issuer_did)

    if not ok:
        print("Cred def was not registered")

    return cred_def, schema


class AirCompany:

    def __init__(self, hub_credentials: dict, pairwises: List[sirius_sdk.Pairwise], me: sirius_sdk.Pairwise.Me):
        self.hub_credentials: dict = hub_credentials
        self.pairwises: List[sirius_sdk.Pairwise] = pairwises
        self.me: sirius_sdk.Pairwise.Me = me
        self.covid_microledger_participants = [me.did] + [pw.their.did for pw in pairwises]
        self.covid_positive_names = set()
        self.boarding_passes = dict()

    async def listen(self):
        async with sirius_sdk.context(**self.hub_credentials):  # работаем в контексте авиакомпании (все вызовы выполняются от имени агента авиакомпании)
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if isinstance(event.message, InitRequestLedgerMessage):  # обработка предложения создания микрореестра положительных ковид справок
                    await self.process_init_microledger(event)
                elif isinstance(event.message, ProposeTransactionsMessage):  # получен запрос на добавление транзакции в микрореестр положительных ковид справок
                    await self.process_new_commit(event)

    async def process_init_microledger(self, event: Event):
        machine = MicroLedgerSimpleConsensus(event.pairwise.me)
        ok, _ = await machine.accept_microledger(event.pairwise, event.message)
        if ok:
            print("Microledger for aircompany created successfully")
        else:
            print("Microledger for aircompany creation failed")

    async def process_new_commit(self, event: Event):
        propose: ProposeTransactionsMessage = event.message
        machine = MicroLedgerSimpleConsensus(self.me)
        await machine.accept_commit(event.pairwise, propose)
        
        # проверяем, если ли среди вновь добавленных ковид положительных тестов наши пассажиры. 
        # Если есть, то им отправляется сообщение об отзыве их посадочного талона
        for tr in propose.transactions:
            test_res = tr["test_res"]
            if test_res["has_covid"]:
                self.covid_positive_names.add(test_res["full_name"])

                for did, boarding_pass in self.boarding_passes.items():
                    if test_res["full_name"] == boarding_pass["full_name"]:
                        pw = await sirius_sdk.PairwiseList.load_for_did(did)
                        msg = sirius_sdk.aries_rfc.Message(
                            content="We have to revoke your boarding pass due to positive covid test", locale="en")
                        await sirius_sdk.send_to(msg, pw)

            else:
                self.covid_positive_names.remove(test_res["full_name"])

    async def register(self, cred_def: sirius_sdk.CredentialDefinition, schema: sirius_sdk.Schema, boarding_pass: dict):
        async with sirius_sdk.context(**self.hub_credentials):  # работаем от имени агента авиакомпании
            connection_key = await sirius_sdk.Crypto.create_key()  # создаем случайный уникальный ключ соединения между агентом авиакомпании и сириус коммуникатором пользователя
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0]  # точка подключения к агенту авиакомпании (интернет адрес)
            invitation = sirius_sdk.aries_rfc.Invitation(  # Создаем приглашение пользователю подключиться к авиакомпании
                label="Getting the boarding pass",
                recipient_keys=[connection_key],
                endpoint=simple_endpoint.address
            )

            qr_content = invitation.invitation_url
            qr_url = await sirius_sdk.generate_qr_code(qr_content)  # агент авиакомпании генерирует уникальный qr код для ранее созданного приглашения

            # пользователь сканирует qr код при помощи sirius коммуникатора. Коммуникатор отправляет агенту авиакомпании запрос на подключение
            print("Scan this QR by Sirius App for receiving the boarding pass " + qr_url)

            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if event.recipient_verkey == connection_key and isinstance(event.message,
                                                                           sirius_sdk.aries_rfc.ConnRequest):
                    # агент авиакомпании получает запрос от пользователя на подключение (запрос соответствкет ранее сгенерированному уникальному ключу соединения)
                    request: sirius_sdk.aries_rfc.ConnRequest = event.message
                    #  агент авиакомпании создает уникальный децентрализованный идентификатор (did) для связи с пользователем (который тоже создает уникальный did для этого соединения)
                    my_did, my_verkey = await sirius_sdk.DID.create_and_store_my_did()
                    sm = sirius_sdk.aries_rfc.Inviter(
                        me=sirius_sdk.Pairwise.Me(
                            did=my_did,
                            verkey=my_verkey
                        ),
                        connection_key=connection_key,
                        my_endpoint=simple_endpoint
                    )
                    # Запускается процесс установки соединения в соответствии с открытым протоколом Aries 0160
                    success, p2p = await sm.create_connection(request)
                    if success:
                        # соединение успешно установлено, о чем сообщается пользователю путем отправки простого текстового сообщения на его сириус коммуникатор
                        message = sirius_sdk.aries_rfc.Message(
                            content="Dear " + boarding_pass["full_name"] + " , welcome to the registration!",
                            locale="en"
                        )
                        await sirius_sdk.send_to(message, p2p)

                        # Если пользователь нраходится в микрореестре ковид-положительных, то посадочный талон ему не выдается
                        if boarding_pass["full_name"] in self.covid_positive_names:
                            message = sirius_sdk.aries_rfc.Message(
                                content="Sorry, we can't issue the boarding pass. Get rid of covid first!",
                                locale="en"
                            )
                            await sirius_sdk.send_to(message, p2p)
                            return

                        issuer = sirius_sdk.aries_rfc.Issuer(p2p)
                        cred_id = "cred-id-" + uuid.uuid4().hex
                        preview = [sirius_sdk.aries_rfc.ProposedAttrib(key, str(value)) for key, value in
                                   boarding_pass.items()]
                        translation = [
                            sirius_sdk.aries_rfc.AttribTranslation("full_name", "Patient Full Name"),
                            sirius_sdk.aries_rfc.AttribTranslation("flight", "Flight num."),
                            sirius_sdk.aries_rfc.AttribTranslation("departure", "Departure"),
                            sirius_sdk.aries_rfc.AttribTranslation("arrival", "Arrival"),
                            sirius_sdk.aries_rfc.AttribTranslation("date", "Date"),
                            sirius_sdk.aries_rfc.AttribTranslation("class", "class"),
                            sirius_sdk.aries_rfc.AttribTranslation("seat", "seat")
                        ]
                        # авиакомпания выдает посадочный талон пользователю.
                        # Посадочный талон оформлен в соответствии с ранее зареестрированной схемой и подписан ЦП авиакомпании.
                        # Пользователь сохраняет посадочный талон на своем сириус коммуникаторе
                        ok = await issuer.issue(
                            values=boarding_pass,
                            schema=schema,
                            cred_def=cred_def,
                            preview=preview,
                            translation=translation,
                            comment="Here is your boarding pass",
                            locale="en"
                        )
                        if ok:
                            print("Boarding pass was successfully issued")
                            # на случай необходимости связаться с пользователем в дальнейшем, сохраним установленное с ним соединение,
                            # его децентрализованный идентификатор (DID) и его посадочный талон
                            await sirius_sdk.PairwiseList.create(p2p)
                            self.boarding_passes[p2p.their.did] = boarding_pass
                        else:
                            print("ERROR while issuing boarding pass")

                    break


async def create_boarding_pass_creds(issuer_did: str) -> (sirius_sdk.CredentialDefinition, sirius_sdk.Schema):
    schema_name = "Boarding Pass"
    # создаем схему (форму) посадочного талона с полями "full_name", "flight", "departure" и т д
    schema_id, anon_schema = await sirius_sdk.AnonCreds.issuer_create_schema(issuer_did, schema_name, '1.0',
                                         ["full_name", "flight", "departure", "arrival", "date", "class", "seat"])
    l = await sirius_sdk.ledger(DKMS_NAME)
    # если схемы посадочного талона нет в распределенном реестре, то ее нужно туда записать, чтобы другие участики могли ей воспользоваться
    schema = await l.ensure_schema_exists(anon_schema, issuer_did)
    if not schema:
        ok, schema = await l.register_schema(anon_schema, issuer_did)
        if ok:
            print("Boarding pass schema registered successfully")
        else:
            print("Boarding pass schema was not registered")
            return None, None

    else:
        print("Boarding pass schema is exists in the ledger")

    ok, cred_def = await l.register_cred_def(
        cred_def=sirius_sdk.CredentialDefinition(tag='TAG', schema=schema),
        submitter_did=issuer_did)

    if not ok:
        print("Cred def was not registered")

    return cred_def, schema


class Airport:

    def __init__(self, hub_credentials: dict, lab_did: str, aircompany_did: str):
        self.hub_credentials = hub_credentials
        self.lab_did = lab_did
        self.aircompany_did = aircompany_did

    async def listen(self):
        async with sirius_sdk.context(**self.hub_credentials):  # работаем в контексте аэропорта (все вызовы выполняются от имени агента аэропорта)
            listener = await sirius_sdk.subscribe()
            async for event in listener:
                if isinstance(event.message, InitRequestLedgerMessage):  # обработка предложения создания микрореестра положительных ковид справок
                    await self.process_init_microledger(event)
                elif isinstance(event.message, ProposeTransactionsMessage):  # получен запрос на добавление транзакции в микрореестр положительных ковид справок
                    await self.process_new_commit(event)

    async def process_init_microledger(self, event: Event):
        machine = MicroLedgerSimpleConsensus(event.pairwise.me)
        ok, _ = await machine.accept_microledger(event.pairwise, event.message)
        if ok:
            print("Microledger for airport created successfully")
        else:
            print("Microledger for airport creation failed")

    async def process_new_commit(self, event: Event):
        machine = MicroLedgerSimpleConsensus(self.me)
        await machine.accept_commit(event.pairwise, event.message)

    async def enter_to_terminal(self):
        async with sirius_sdk.context(**self.hub_credentials): # работаем в контексте аэропорта (все вызовы будут происходить от имени агента аэропорта)
            connection_key = await sirius_sdk.Crypto.create_key() # создаем случайный уникальный ключ соединения между агентом аэропорта и сириус коммуникатором пользователя
            endpoints = await sirius_sdk.endpoints()
            simple_endpoint = [e for e in endpoints if e.routing_keys == []][0] # точка подключения к агенту аэропорта (интернет адрес)
            invitation = sirius_sdk.aries_rfc.Invitation(  # Создаем приглашение пользователю подключиться к аэропорту
                label="Terminal",
                recipient_keys=[connection_key],
                endpoint=simple_endpoint.address
            )

            qr_content = invitation.invitation_url
            qr_url = await sirius_sdk.generate_qr_code(qr_content) # агент аэропорта генерирует уникальный qr код для ранее созданного приглашения

            # пользователь сканирует qr код при помощи sirius коммуникатора. Коммуникатор отправляет агенту аэропорта запрос на подключение
            print("Scan this QR by Sirius App to enter to the terminal " + qr_url)

            listener = await sirius_sdk.subscribe()
            while True:
                event = await listener.get_one()
                if event.recipient_verkey == connection_key and isinstance(event.message,
                                                                           sirius_sdk.aries_rfc.ConnRequest):
                    # агент аэропорта получает запрос от пользователя на подключение (запрос соответствкет ранее сгенерированному уникальному ключу соединения)
                    request: sirius_sdk.aries_rfc.ConnRequest = event.message
                    #  агент аэропорта создает уникальный децентрализованный идентификатор (did) для связи с пользователем (который тоже создает уникальный did для этого соединения)
                    did, verkey = await sirius_sdk.DID.create_and_store_my_did()
                    inviter = sirius_sdk.aries_rfc.Inviter(sirius_sdk.Pairwise.Me(did, verkey), connection_key, simple_endpoint)
                    # Запускается процесс установки соединения в соответствии с открытым протоколом Aries 0160
                    ok, pw = await inviter.create_connection(request)

                    if not ok:
                        print("connection failed")
                        break

                    # соединение успешно установлено, о чем сообщается пользователю путем отправки простого текстового сообщения на его сириус коммуникатор
                    message = sirius_sdk.aries_rfc.Message(
                        content="Welcome to the airport!",
                        locale="en"
                    )
                    await sirius_sdk.send_to(message, pw)

                    # для прохода в аэропорт требуется предъявить справку о ковид, выданную лабораторией, и посадочный талон, выданный авиакомпанией
                    # аэропорт создает запрос документов с требованиями к ним
                    proof_request = {
                        "nonce": await sirius_sdk.AnonCreds.generate_nonce(),
                        "name":  "Verify false covid test",
                        "version": "1.0",
                        "requested_attributes": {
                            "attr1_referent": {
                                "name": "has_covid",
                                "restrictions": {
                                    "issuer_did": self.lab_did # требуется, чтобы ковид справка была выдана соответствующей лабораторией
                                }
                            },
                            "attr2_referent": {
                                "name": "flight",
                                "restrictions": {
                                    "issuer_did": self.aircompany_did # требуется, чтобы посадочный талон был выдан авиакомпанией
                                }
                            }
                        }
                    }

                    ver_ledger = await sirius_sdk.ledger(DKMS_NAME)
                    verifier = sirius_sdk.aries_rfc.Verifier(pw, ver_ledger, logger=Logger())
                    # на основе отркытого протокола Aries 0037 происходит проверка документов, предоставленных пользователем (ковид справки и посадочного талона)
                    ok = await verifier.verify(proof_request=proof_request, comment="Verify covid test and boarding pass")
                    if ok:
                        has_covid = bool(verifier.requested_proof["revealed_attrs"]["attr1_referent"]["raw"])
                        if has_covid:
                            # пользователю с положительной справкой о ковид в доступе в аэропорт будет отказано
                            msg = sirius_sdk.aries_rfc.Message(
                                content="Sorry, but we can't let your go to the terminal. Please, get rid of covid first!",
                                locale="en"
                            )
                            await sirius_sdk.send_to(msg, pw)
                        else:
                            # Если все документы в порядке, пользователь может пройти в терминал
                            msg = sirius_sdk.aries_rfc.Message(
                                content="Welcome on board!",
                                locale="en"
                            )
                            await sirius_sdk.send_to(msg, pw)
                    else:
                        print("verification failed")

                    break


if __name__ == '__main__':
    med_cred_def: sirius_sdk.CredentialDefinition
    med_schema: sirius_sdk.Schema
    boarding_pass_cred_def: sirius_sdk.CredentialDefinition
    boarding_pass_schema: sirius_sdk.Schema

    # реестрация формы результатов анализа на ковид и посадочного талона в блокчейне
    async def init_creds():
        global med_cred_def, med_schema, boarding_pass_cred_def, boarding_pass_schema
        async with sirius_sdk.context(**LABORATORY['sdk']):  # работаем в контексте ковид-лаборатории (все вызовы будут происходить от имени агента ковид-лаборатории)
            # ковид лаборатория выпускает стандартизированную схему (форму) теста на ковид
            med_cred_def, med_schema = await create_med_creds(LABORATORY['did'])
        async with sirius_sdk.context(**AIR_COMPANY['sdk']):  # работаем в контексте авиакомпании (все вызовы будут происходить от имени агента авиакомпании)
            # авиакомпания выпускает стандартизированную схему (форму) посадочного талона
            boarding_pass_cred_def, boarding_pass_schema = await create_boarding_pass_creds(AIR_COMPANY['did'])

    asyncio.get_event_loop().run_until_complete(init_creds())

    # для создания децентрализованного микрореестра положительных ковид тестов необходимо установить соединение между участниками (лабораторией и авиакомпанией)
    lab_to_ac = establish_connection(LABORATORY['sdk'], LABORATORY["did"], AIR_COMPANY['sdk'], AIR_COMPANY["did"])
    ac_to_lab = establish_connection(AIR_COMPANY['sdk'], AIR_COMPANY["did"], LABORATORY['sdk'], LABORATORY["did"])

    # создание классов, обслуживающих работу лабы, авиакомпании и аэропорта
    lab = Laboratory(hub_credentials=LABORATORY['sdk'], pairwises=[lab_to_ac], me=lab_to_ac.me)
    air_company = AirCompany(hub_credentials=AIR_COMPANY['sdk'], pairwises=[ac_to_lab], me=ac_to_lab.me)
    airport = Airport(hub_credentials=AIRPORT['sdk'], lab_did=LABORATORY["did"], aircompany_did=AIR_COMPANY["did"])

    # слушаем входящие сообщения
    asyncio.ensure_future(lab.listen())
    asyncio.ensure_future(air_company.listen())
    asyncio.ensure_future(airport.listen())

    async def run():
        full_name = input("Enter your name:")
        loop = True
        while loop:
            print("Enter your option:")
            print("1 - Get Covid test")
            print("2 - Get boarding pass")
            print("3 - Enter to the terminal")
            print("4 - Exit")
            case = int(input())
            if case == 1:
                has_covid = input("Do you have Covid? (yes/no)").lower() == "yes"
                # заполняем результаты теста в соответствии со схемой
                covid_test_res = {
                    "full_name": full_name,
                    "has_covid": has_covid,
                    "location": "Nur-Sultan",
                    "bio_location": "Nur-Sultan",
                    "approved": "House M.D.",
                    "timestamp": str(datetime.datetime.now())
                }
                # выдаем результаты пользователю при помощи qr кода и sirius коммуникатора
                await lab.issue_test_results(med_cred_def, med_schema, covid_test_res)
            elif case == 2:
                # заполняем посадочный талон в соответствии со схемой
                boarding_pass = {
                    "full_name": full_name,
                    "arrival": "Nur-Sultan",
                    "departure": "New York JFK",
                    "class": "first",
                    "date": str(datetime.datetime.now()),
                    "flight": "KC 1234",
                    "seat": "1A"
                }
                # выдаем посадочный талон пользователю при помощи qr кода и sirius коммуникатора
                await air_company.register(boarding_pass_cred_def, boarding_pass_schema, boarding_pass)
            elif case == 3:
                # моделируем процесс входа пользователя с сириус коммуникатором в терминал аэропорта
                await airport.enter_to_terminal()
            else:
                loop = False

    asyncio.get_event_loop().run_until_complete(run())