"""Example for Cover device."""
import asyncio

from xknx import XKNX
from xknx.devices import Cover


async def main():
    """Connect to KNX/IP device, Set up outlet, wait 2 seconds, Set down, wait 2 seconds and stop."""
    xknx = XKNX()
    await xknx.start()
    cover = Cover(xknx,
                    name='TestOutlet',
                    group_address_long='1/3/81',
                    group_address_short='1/3/85',
                    group_address_position_state='1/3/91')
    await cover.sync()
    await cover.set_up()
    await asyncio.sleep(2)
    await cover.set_down()
    await asyncio.sleep(2)
    await cover.stop()
    await cover.sync()

    print(cover)

    await xknx.stop()


# pylint: disable=invalid-name
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
