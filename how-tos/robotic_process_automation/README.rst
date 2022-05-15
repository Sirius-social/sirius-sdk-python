=========================================
Robotic process automation
=========================================
**Sirius SDK** provides tools to automate communication between your customers and employee,
involving them to the business process avoiding necessity for humans to deep dive into the procedural issues.
**Sirius** offers to implement `Robotic process automation <https://en.wikipedia.org/wiki/Robotic_process_automation>`_
concept via **Virtual Assistants** (like Telegram/WhatsApp chat bots)


Preparing for test live demo
=================================
1. Install **Indy Edge Agent** compatible with Aries RFCs features `0095 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0095-basic-message>`_
   `0113 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0113-question-answer>`_
   `0036 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0036-issue-credential>`_
   `0037 <https://github.com/hyperledger/aries-rfcs/tree/master/features/0037-present-proof>`_ .
   For example you may download `Sirius communicator for Android <https://yadi.sk/d/tdxYKNC37s3VOA>`_
2. To play DEMO run script `main.py <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/robotic_process_automation/main.py>`_

   .. code-block:: bash

      python main.py

   or you may run it in debugger to check how it works step-by-step.

3. Scan QR code of **Sirius Bank** virtual assistance to get digital service from bank.

   .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/bank_qr2.png?raw=true
     :height: 200px
     :width: 200px
     :alt: Bank

   Assume that the bank has already processed **KYC** requirements and linked correspondent services to your P2P Pairwise.
   You will can see that in order to get digital **"Loan request"** you should first get salary credential from your employer.

   .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/loan_declined.jpeg?raw=true
     :alt: Loan declined

4.  Then let's navigate to QR code to establish connection with Demo employer...

   .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/employer_qr2.png?raw=true
     :height: 200px
     :width: 200px
     :alt: Employer

   Assume that employer has processed **KYC** requirements and may identify you by Pairwise connection.
   You can see among several digital services that provided by demo employer, you
   can request for **salary credentials**...

   .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/issue_salary_creds2.jpeg?raw=true
     :alt: Issued salary credential

5. Come back to Bank and try again to request the **Loan**

   .. image:: https://github.com/Sirius-social/sirius-sdk-python/blob/master/docs/_static/verify_salary_creds2.jpeg?raw=true
     :alt: Verify salary credential by Bank


Sample code
=================================
The source code for playing DEMO is located `here <https://github.com/Sirius-social/sirius-sdk-python/blob/master/how-tos/robotic_process_automation/main.py>`_

Let's pay attention to the source code presented below:

.. code-block:: python

    listener = await sirius_sdk.subscribe()
    async for event in listener:
        # Here developer place code to react to participant action




Virtual assistant may provide menu for different use-cases

.. code-block:: python

    ask = sirius_sdk.aries_rfc.Question(
        valid_responses=[service1, service2, service3],
        question_text=f'{person_name} welcome!',
        question_detail='I am your employer Virtual Assistant.',
        locale='en'
    )
    ask.set_ttl(60)  # Set timeout for answer
    success, answer = await sirius_sdk.recipes.ask_and_wait_answer(
        query=ask,
        to=dialog_pairwise
    )


Conclusions
==================
In the presented example the trust among Bank and Employer was established avoiding the necessity for
both of them to configure P2P relationships and develop difficult consensus procedures.
Bank maintains self managed root-of-trust, so it can accept credentials issued by employer **X**
because it is bank decision. Anon-Creds concept helps to cover trust issues avoiding to build
direct relationship. Moreover, credential owner controls his data.

Building trusted environment to reduce transaction cost is a complex task.
Sirius communicator developed as **Indy Edge Agent**, is a part of relationship building
in a human-friendly form (customers, employees, etc.).
Another part of complexity is developing business/gov side of relationship
via **Sirius SDK** solution that reduces time and costs to implement work processes
in trusted environment.

Human was involved into demo business process in a user friendly manner thanks to
Virtual Assistance driven on Server-side of the independent companies (Bank & Employer)
that was developed with **Sirius SDK**

