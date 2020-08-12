import os
import sys
import time

import click
import RPi.GPIO as GPIO
from ADCDACPi import ADCDACPi as ADC


GPIO.setmode(GPIO.BOARD)

ADC_REFERENCE_VOLTAGE = 3.3
ADC_READ_MODE_SINGLE = 0
ADC_READ_INTERVAL = 0.25

SOIL_ADC_CHANNEL = 1
WATER_ADC_CHANNEL = 2

SOIL_DRY_THRESHOLD = 2.5
WATER_LEVEL_WARNING_THRESHOLD = 3.0
WATER_LEVEL_CRITICAL_THRESHOLD = 2.7

RELAY_PIN_NUMBER = 10

WATER_LEVEL_CRITICAL_MESSAGE = (
    "The water level is critically low! "
    "Refill the tank to continue watering."
)
WATER_LEVEL_WARNING_MESSAGE = "The water level is low."
SOIL_IS_WET_MESSAGE = "The soil is wet."
TIME_IS_UP_MESSAGE = "The time is up."
STOPPING_PUMP_MESSAGE = "Stopping the pump."


class Pin:
    def __init__(self, number, direction):
        self.number = number
        self._direction = direction
        GPIO.setup(self.number, self._direction)

    @property
    def _current_state(self):
        raise NotImplementedError("Must be implemented in subclasses.")

    @property
    def is_high(self):
        return self._current_state == GPIO.HIGH

    @property
    def is_low(self):
        return self._current_state == GPIO.LOW


class InputPin(Pin):
    def __init__(self, number):
        super().__init__(number, GPIO.IN)

    @property
    def _current_state(self):
        return GPIO.input(self.number)

    @property
    def value(self):
        return self._current_state


class OutputPin(Pin):
    def __init__(self, number):
        super().__init__(number, GPIO.OUT)
        self._current_output = GPIO.LOW

    @property
    def _current_state(self):
        return self._current_output

    def _set_output(self, value):
        self._current_output = value
        GPIO.output(self.number, self._current_output)

    def set_high(self):
        return self._set_output(GPIO.HIGH)

    def set_low(self):
        return self._set_output(GPIO.LOW)


def _echo(*args):
    click.echo(" ".join(str(arg) for arg in args))


def cleanup():
    GPIO.cleanup()


def to_stdout(s):
    terminal_width = os.get_terminal_size().columns
    number_of_extra_spaces = terminal_width - len(s)
    full_line = s + " " * number_of_extra_spaces
    sys.stdout.write(full_line)
    sys.stdout.flush()
    sys.stdout.write("\r")
    sys.stdout.flush()


def read_adc(adc, channel):
    return adc.read_adc_voltage(channel, ADC_READ_MODE_SINGLE)


def is_water_level_low(adc):
    return read_adc(adc, WATER_ADC_CHANNEL) < WATER_LEVEL_WARNING_THRESHOLD


def is_water_level_critical(adc):
    return read_adc(adc, WATER_ADC_CHANNEL) < WATER_LEVEL_CRITICAL_THRESHOLD


def is_soil_dry(adc):
    return read_adc(adc, SOIL_ADC_CHANNEL) > SOIL_DRY_THRESHOLD


def run_pump(adc, timeout, check_water_level=True, check_moisture=True):
    if check_moisture:
        _echo(
            "Running pump until the soil is wet or "
            "for at most {} seconds.".format(timeout)
        )
    else:
        _echo("Running pump for {} seconds.".format(timeout))

    relay_pin = OutputPin(RELAY_PIN_NUMBER)
    relay_pin.set_high()

    stop_time = time.time() + timeout
    while True:
        if check_water_level and is_water_level_critical(adc):
            _echo(WATER_LEVEL_CRITICAL_MESSAGE)
            break
        if check_moisture and not is_soil_dry(adc):
            _echo(SOIL_IS_WET_MESSAGE)
            break
        if time.time() >= stop_time:
            _echo(TIME_IS_UP_MESSAGE)
            break

    _echo(STOPPING_PUMP_MESSAGE)
    relay_pin.set_low()

    if check_water_level and is_water_level_low(adc):
        _echo(WATER_LEVEL_WARNING_MESSAGE)


def check_sensors_and_run_pump(adc, timeout):
    if is_water_level_critical(adc):
        _echo(WATER_LEVEL_CRITICAL_MESSAGE)
        exit()

    if is_water_level_low(adc):
        _echo(WATER_LEVEL_WARNING_MESSAGE)

    if is_soil_dry(adc):
        _echo("The soil is dry.")
        run_pump(adc, timeout)
    else:
        _echo(SOIL_IS_WET_MESSAGE)


def run_and_cleanup(runner, *runner_args, **runner_kwargs):
    try:
        adc = ADC()
        adc.set_adc_refvoltage(ADC_REFERENCE_VOLTAGE)
        runner(*runner_args, **runner_kwargs)
    finally:
        cleanup()


@click.group()
def spiracle():
    pass


@spiracle.command()
@click.argument("channel", type=click.INT)
def debug(channel):
    adc = ADC()
    adc.set_adc_refvoltage(ADC_REFERENCE_VOLTAGE)

    def output_line(value):
        return "ADC channel {} is showing {} V".format(channel, value)

    def read_adc():
        return adc.read_adc_voltage(channel, ADC_READ_MODE_SINGLE)

    while True:
        voltage = read_adc()
        line = output_line(voltage)
        to_stdout(line)
        time.sleep(ADC_READ_INTERVAL)


@spiracle.command()
@click.argument("timeout", type=click.FLOAT)
@click.option("--water-level-sensor", is_flag=True, default=False)
@click.option("--moisture-sensor", is_flag=True, default=False)
def pump(timeout, water_level_sensor, moisture_sensor):
    run_and_cleanup(run_pump, timeout, water_level_sensor, moisture_sensor)


@spiracle.command()
@click.argument("timeout", type=click.FLOAT)
def run(timeout):
    run_and_cleanup(check_sensors_and_run_pump, timeout)


if __name__ == "__main__":
    spiracle()
