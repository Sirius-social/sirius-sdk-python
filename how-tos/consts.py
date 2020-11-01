import sirius_sdk


AGENT1 = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/C/MUJCo8OmN4AMVmddE/sew8gBzsOg040FWBSXzHd9hDoj5B5KN4aaLiyzTqkrbD3uaeSwmvxVsqkC0xl5dtIc='.encode(),
    'p2p': sirius_sdk.P2PConnection(
            my_keys=('6QvQ3Y5pPMGNgzvs86N3AQo98pF5WrzM1h6WkKH3dL7f', '28Au6YoU7oPt6YLpbWkzFryhaQbfAcca9KxZEmz22jJaZoKqABc4UJ9vDjNTtmKSn2Axfu8sT52f5Stmt7JD4zzh'),
            their_verkey='6oczQNLU7bSBzVojkGsfAv3CbXagx7QLUL7Yj1Nba9iw'
        )
}


AGENT2 = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/NRtCY78r2bCZO8nJ7ooWxDa6TQbCWUvnpylTJSRnMq3Doj5B5KN4aaLiyzTqkrbDwMKo4RJ3alpnUUd4iyxgqE='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('5o6wXAYT3A8svdog2t4M3gk15iXNW8yvxVu3utJHAD7g', '2xsAzx4URZGY8imWRL5jFAbQqvdFHw4ZbuxxoAADSqVCFTbiwZYhw4gPVA5dsqbJSsLxbac7ath4sFiHYzyVsEDY'),
        their_verkey='GoPE3ZkJXKjrNnP8LdJuzhbxKjAwND8Q9vSosqzTeAJd'
    )
}


AGENT3 = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/P+YgoaBDJV7S03Nxc26pIVlgwkbSZ0XjQ9fEVd4Xrq+Doj5B5KN4aaLiyzTqkrbD8j/KbG7UG4Jfx2kkFcXAvc='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('6RZN88AEYsYQH6WXyunMt8JXLFjenDqrRGeQayG5zY15', '265jVEbBup5EJ9pHJrrRWDnm5rxcZhHkn6FPbcH1su9HMT28yv8BHwithHT8PnFxx91zPVeBiXBvTywqLk3P3vfh'),
        their_verkey='FCzrVZqZbn1PAJQNSqgaLP6DXZhKKUtK5wU3TNnG7d5P'
    )
}


AGENT4 = {
    'server_uri': 'https://demo.socialsirius.com',
    'credentials': 'ez8ucxfrTiV1hPX99MHt/JZL1h63sUO9saQCgn2BsaC2EndwDSYpOo6eFpn8xP8ZDoj5B5KN4aaLiyzTqkrbDxrbAe/+2uObPTl6xZdXMBs='.encode(),
    'p2p': sirius_sdk.P2PConnection(
        my_keys=('B1n1Hwj1USs7z6FAttHCJcqhg7ARe7xtcyfHJCdXoMnC', 'y7fwmKxfatm6SLN6sqy6LFFjKufgzSsmqA2D4WZz55Y8W7JFeA3LvmicC36E8rdHoAiFhZgSf4fuKmimk9QyBec'),
        their_verkey='5NUzoX1YNm5VXsgzudvVikN7VQpRf5rhaTnPxyu12eZC'
    )
}


PROVER_SECRET_ID = 'prover-secret-id'
