"""
Module for managing a remote value KNX.

Remote value can either be a group address for reading
and and one group address for writing a KNX value
or a group address for both.
"""
from enum import Enum

from xknx.exceptions import ConversionError, CouldNotParseTelegram
from xknx.knx import (DPTArray, DPTBinary, DPTScaling, DPTSceneNumber,
                      DPTTemperature, DPTValue1Count, GroupAddress, Telegram,
                      TelegramType)


class RemoteValue():
    """Class for managing remote knx value."""

    def __init__(self,
                 xknx,
                 group_address=None,
                 group_address_state=None,
                 device_name=None,
                 after_update_cb=None):
        """Initialize RemoteValue class."""
        # pylint: disable=too-many-arguments
        self.xknx = xknx
        if isinstance(group_address, (str, int)):
            group_address = GroupAddress(group_address)
        if isinstance(group_address_state, (str, int)):
            group_address_state = GroupAddress(group_address_state)

        self.group_address = group_address
        self.group_address_state = group_address_state
        self.after_update_cb = after_update_cb
        self.device_name = "Unknown" \
            if device_name is None else device_name
        self.payload = None

    @property
    def initialized(self):
        """Evaluate if remote value is initialized with group address."""
        return bool(self.group_address_state or self.group_address)

    def has_group_address(self, group_address):
        """Test if device has given group address."""
        return (self.group_address == group_address) or \
               (self.group_address_state == group_address)

    def state_addresses(self):
        """Return group addresses which should be requested to sync state."""
        if self.group_address_state:
            return [self.group_address_state, ]
        if self.group_address:
            return [self.group_address, ]
        return []

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed - to be implemented in derived class.."""
        # pylint: disable=unused-argument
        self.xknx.logger.warning("payload_valid not implemented for %s", self.__class__.__name__)
        return True

    def from_knx(self, payload):
        """Convert current payload to value - to be implemented in derived class."""
        # pylint: disable=unused-argument
        self.xknx.logger.warning("from_knx not implemented for %s", self.__class__.__name__)
        return None

    def to_knx(self, value):
        """Convert value to payload - to be implemented in derived class."""
        # pylint: disable=unused-argument
        self.xknx.logger.warning("to_knx not implemented for %s", self.__class__.__name__)
        return None

    async def process(self, telegram):
        """Process incoming telegram."""
        if not self.has_group_address(telegram.group_address):
            return False
        if not self.payload_valid(telegram.payload):
            raise CouldNotParseTelegram("payload invalid",
                                        payload=telegram.payload,
                                        group_address=telegram.group_address,
                                        device_name=self.device_name)
        if self.payload != telegram.payload:
            self.payload = telegram.payload
            if self.after_update_cb is not None:
                await self.after_update_cb()
        return True

    @property
    def value(self):
        """Return current value ."""
        if self.payload is None:
            return None
        return self.from_knx(self.payload)

    async def send(self, response=False):
        """Send payload as telegram to KNX bus."""
        telegram = Telegram()
        telegram.group_address = self.group_address
        telegram.telegramtype = TelegramType.GROUP_RESPONSE \
            if response else TelegramType.GROUP_WRITE
        telegram.payload = self.payload
        await self.xknx.telegrams.put(telegram)

    async def set(self, value):
        """Set new value."""
        if not self.initialized:
            self.xknx.logger.info("Setting value of uninitialized device %s (value %s)", self.device_name, value)
            return
        payload = self.to_knx(value)
        updated = False
        if self.payload is None or payload != self.payload:
            self.payload = payload
            updated = True
        await self.send()
        if updated and self.after_update_cb is not None:
            await self.after_update_cb()

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return None

    def group_addr_str(self):
        """Return object as readable string."""
        return '{0}/{1}/{2}/{3}' \
            .format(self.group_address,
                    self.group_address_state,
                    self.payload,
                    self.value)

    def __str__(self):
        """Return object as string representation."""
        return '<{} device_name="{}" {}/>'.format(
            self.__class__.__name__,
            self.device_name,
            self.group_addr_str())

    def __eq__(self, other):
        """Equal operator."""
        for key, value in self.__dict__.items():
            if key == "after_update_cb":
                continue
            if key not in other.__dict__:
                return False
            if other.__dict__[key] != value:
                return False
        for key, value in other.__dict__.items():
            if key == "after_update_cb":
                continue
            if key not in self.__dict__:
                return False
        return True


class RemoteValueSwitch1001(RemoteValue):
    """Abstraction for remote value of KNX DPT 1.001 / DPT_Switch."""

    class Value(Enum):
        """Enum for indicating the direction."""

        # pylint: disable=invalid-name
        OFF = 0
        ON = 1

    def __init__(self,
                 xknx,
                 group_address=None,
                 group_address_state=None,
                 device_name=None,
                 after_update_cb=None,
                 invert=False):
        """Initialize remote value of KNX DPT 1.001."""
        # pylint: disable=too-many-arguments
        super(RemoteValueSwitch1001, self).__init__(
            xknx, group_address, group_address_state,
            device_name=device_name, after_update_cb=after_update_cb)
        self.invert = invert

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return isinstance(payload, DPTBinary)

    def to_knx(self, value):
        """Convert value to payload."""
        if value == self.Value.OFF:
            return DPTBinary(1) if self.invert else DPTBinary(0)
        elif value == self.Value.ON:
            return DPTBinary(0) if self.invert else DPTBinary(1)
        raise ConversionError("value invalid", value=value, device_name=self.device_name)

    def from_knx(self, payload):
        """Convert current payload to value."""
        if payload == DPTBinary(0):
            return self.Value.ON if self.invert else self.Value.OFF
        elif payload == DPTBinary(1):
            return self.Value.OFF if self.invert else self.Value.ON
        raise ConversionError("payload invalid", payload=payload, device_name=self.device_name)

    async def off(self):
        """Set value to down."""
        await self.set(self.Value.OFF)

    async def on(self):
        """Set value to UP."""
        # pylint: disable=invalid-name
        await self.set(self.Value.ON)


class RemoteValueUpDown1008(RemoteValue):
    """Abstraction for remote value of KNX DPT 1.008 / DPT_UpDown."""

    class Direction(Enum):
        """Enum for indicating the direction."""

        # pylint: disable=invalid-name
        UP = 0
        DOWN = 1

    def __init__(self,
                 xknx,
                 group_address=None,
                 group_address_state=None,
                 device_name=None,
                 after_update_cb=None,
                 invert=False):
        """Initialize remote value of KNX DPT 1.008."""
        # pylint: disable=too-many-arguments
        super(RemoteValueUpDown1008, self).__init__(
            xknx, group_address, group_address_state,
            device_name=device_name, after_update_cb=after_update_cb)
        self.invert = invert

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return isinstance(payload, DPTBinary)

    def to_knx(self, value):
        """Convert value to payload."""
        if value == self.Direction.UP:
            return DPTBinary(1) if self.invert else DPTBinary(0)
        elif value == self.Direction.DOWN:
            return DPTBinary(0) if self.invert else DPTBinary(1)
        raise ConversionError("value invalid", value=value, device_name=self.device_name)

    def from_knx(self, payload):
        """Convert current payload to value."""
        if payload == DPTBinary(0):
            return self.Direction.DOWN if self.invert else self.Direction.UP
        elif payload == DPTBinary(1):
            return self.Direction.UP if self.invert else self.Direction.DOWN
        raise ConversionError("payload invalid", payload=payload, device_name=self.device_name)

    async def down(self):
        """Set value to down."""
        await self.set(self.Direction.DOWN)

    async def up(self):
        """Set value to UP."""
        # pylint: disable=invalid-name
        await self.set(self.Direction.UP)


class RemoteValueStep1007(RemoteValue):
    """Abstraction for remote value of KNX DPT 1.007 / DPT_Step."""

    class Direction(Enum):
        """Enum for indicating the direction."""

        DECREASE = 0
        INCREASE = 1

    def __init__(self,
                 xknx,
                 group_address=None,
                 group_address_state=None,
                 device_name=None,
                 after_update_cb=None,
                 invert=False):
        """Initialize remote value of KNX DPT 1.007."""
        # pylint: disable=too-many-arguments
        super(RemoteValueStep1007, self).__init__(
            xknx, group_address, group_address_state,
            device_name=device_name, after_update_cb=after_update_cb)
        self.invert = invert

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return isinstance(payload, DPTBinary)

    def to_knx(self, value):
        """Convert value to payload."""
        if value == self.Direction.INCREASE:
            return DPTBinary(1) if self.invert else DPTBinary(0)
        elif value == self.Direction.DECREASE:
            return DPTBinary(0) if self.invert else DPTBinary(1)
        raise ConversionError("value invalid", value=value, device_name=self.device_name)

    def from_knx(self, payload):
        """Convert current payload to value."""
        if payload == DPTBinary(0):
            return self.Direction.DECREASE if self.invert else self.Direction.INCREASE
        elif payload == DPTBinary(1):
            return self.Direction.INCREASE if self.invert else self.Direction.DECREASE
        raise ConversionError("payload invalid", payload=payload, device_name=self.device_name)

    async def increase(self):
        """Increase value."""
        await self.set(self.Direction.INCREASE)

    async def decrease(self):
        """Decrease the value."""
        await self.set(self.Direction.DECREASE)


class RemoteValueScaling5001(RemoteValue):
    """Abstraction for remote value of KNX DPT 5.001 (DPT_Scaling)."""

    def __init__(self,
                 xknx,
                 group_address=None,
                 group_address_state=None,
                 device_name=None,
                 after_update_cb=None,
                 invert=False):
        """Initialize remote value of KNX DPT 5.001 (DPT_Scaling)."""
        # pylint: disable=too-many-arguments
        super(RemoteValueScaling5001, self).__init__(
            xknx, group_address, group_address_state,
            device_name=device_name, after_update_cb=after_update_cb)
        self.invert = invert

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return (isinstance(payload, DPTArray)
                and len(payload.value) == 1)

    def to_knx(self, value):
        """Convert value to payload."""
        if not self.invert:
            value = 100 - value
        return DPTArray(DPTScaling.to_knx(value))

    def from_knx(self, payload):
        """Convert current payload to value."""
        value = DPTScaling.from_knx(payload.value)
        if not self.invert:
            value = 100 - value
        return value

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"


class RemoteValueSceneNumber17001(RemoteValue):
    """Abstraction for remote value of KNX DPT 17.001 (DPT_Scene_Number)."""

    def __init__(self,
                 xknx,
                 group_address=None,
                 device_name=None,
                 after_update_cb=None):
        """Initialize remote value of KNX DPT 17.001 (DPT_Scene_Number)."""
        # pylint: disable=too-many-arguments
        super(RemoteValueSceneNumber17001, self).__init__(
            xknx, group_address, None,
            device_name=device_name, after_update_cb=after_update_cb)

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return (isinstance(payload, DPTArray)
                and len(payload.value) == 1)

    def to_knx(self, value):
        """Convert value to payload."""
        return DPTArray(DPTSceneNumber.to_knx(value))

    def from_knx(self, payload):
        """Convert current payload to value."""
        return DPTSceneNumber.from_knx(payload.value)


class RemoteValue1Count(RemoteValue):
    """Abstraction for remote value of KNX 6.010 (DPT_Value_1_Count)."""

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return (isinstance(payload, DPTArray)
                and len(payload.value) == 1)

    def to_knx(self, value):
        """Convert value to payload."""
        return DPTArray(DPTValue1Count.to_knx(value))

    def from_knx(self, payload):
        """Convert current payload to value."""
        return DPTValue1Count.from_knx(payload.value)


class RemoteValueTemp(RemoteValue):
    """Abstraction for remote value of KNX 9.001 (DPT_Value_Temp)."""

    def payload_valid(self, payload):
        """Test if telegram payload may be parsed."""
        return (isinstance(payload, DPTArray)
                and len(payload.value) == 2)

    def to_knx(self, value):
        """Convert value to payload."""
        return DPTArray(DPTTemperature.to_knx(value))

    def from_knx(self, payload):
        """Convert current payload to value."""
        return DPTTemperature.from_knx(payload.value)
