# hildebrand_glow_ihd
Hildebrand Glow IHD Local MQTT Home Assistant integration - Extended
This fork supports Hildebrand Glow Thermal Sensors, and includes some other changes

Inspired and heavily based on [@robertalexa](https://github.com/robertalexa) forum thread here: https://community.home-assistant.io/t/glow-hildebrand-display-local-mqtt-access-template-help/428638

# Guide

## Installation & Usage

1. Install MQTT Addon (https://home-assistant.io/components/mqtt/) - required for this integration to work
2. Buy a Hildebrand Glow IHD device (https://shop.glowmarkt.com/products/display-and-cad-combined-for-smart-meter-customers)
3. Follow this blog post to connect the Hildebrand Glow IHD device (https://medium.com/@joshua.cooper/glow-local-mqtt-f69b776b7af4)
4. Add repository to HACS (see https://hacs.xyz/docs/faq/custom_repositories) - use "https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt" as the repository URL.
5. Install the `hildebrand_glow_ihd_mqtt` integration inside HACS
6. Restart HA
7. Add Hildebrand Glow IHD MQTT integration using the normal HA integration configuration screen - note if you leave the Device ID as '+' it will automatically detect all Hildebrand Glow IHD devices publishing to your MQTT - this is the recommended way.
8. Your various `sensor`s will be named something like `sensor.smart_meter...` grouped as devices.

![image](https://user-images.githubusercontent.com/1478003/173249987-4724af89-ceaa-4422-a426-4b8a2b16d98e.png)
