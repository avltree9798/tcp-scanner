from itertools import product

import argparse
import asyncio
import logging
import ipaddress
import json

MAX_WORKER_SIZE = 500

logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

async def check_port(ip_address: str, port: int) -> str:
    logger.info(f"Checking {ip_address}:{port}")
    future = asyncio.open_connection(ip_address, port, loop=None)
    try:
        future = await asyncio.wait_for(future, 0.1)
    except asyncio.TimeoutError:
        pass
    except Exception as exc:
        logger.error('Error {}:{} {}'.format(ip_address, port, exc))
    return {
        'ip_address': ip_address,
        'port': port,
        'future': future
    }


async def consumer(queue, result_queue, include_close):
    while True:
        await asyncio.sleep(0.1)
        try:
            ip, port = queue.get_nowait()
            result = await check_port(ip, port)
            add_to_result_queue = include_close
            data = {
                'ip_address': result.get('ip_address'),
                'port': result.get('port'),
                'status': 'close'
            }
            if isinstance(result.get('future'), tuple):
                data['status'] = 'open'
                add_to_result_queue = True
            
            if add_to_result_queue:
                result_queue.append(data)
        except asyncio.queues.QueueEmpty:
            break
        except Exception as e:
            logger.exception(f"Uncaught exception at consumer: {e}")
            break


async def producer(queue, argv):
    ip_addresses = []
    try:
        ip_addresses = [str(ipaddress.IPv4Address(argv.ip))]
    except ipaddress.AddressValueError:
        ip_addresses = [str(ip) for ip in ipaddress.IPv4Network(argv.ip)]
    except Exception as e:
        logger.exception(f"Uncaught exception at producer: {e}")
        return
    ports = [int(port) for port in argv.ports.split(",")]

    for ip, port in product(ip_addresses, ports):
        queue.put_nowait((ip, port))

async def main(loop, argv):
    result_queue = []
    scan_queue = asyncio.Queue()
    tasks = [
        asyncio.create_task(producer(scan_queue, argv))
    ]
    for i in range(MAX_WORKER_SIZE):
        tasks.append(
            asyncio.create_task(consumer(scan_queue, result_queue, argv.include_close))
        )
    
    await asyncio.wait(tasks)
    result = json.dumps(result_queue)
    if argv.output == 'stdout':
        print(result)
        return
    
    with open(argv.output, "w+") as f:
        f.write(result)
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TCP Port Scanner')
    parser.add_argument('--ip', help='IP Address or IP Address/CIDR', type=str, required=True)
    parser.add_argument('--ports', help='Ports separated by comma. Default value: 22,80,443', type=str, default='22,80,443')
    parser.add_argument('--include-close', help='Include closed port on the result', action=argparse.BooleanOptionalAction)
    parser.add_argument('--output', help='Path to output. Default value: stdout', type=str, default='stdout')
    argv = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop, argv))
    loop.close()

