from omega_protocol.system import build_media_capabilities, media_by_drive_letter


def test_build_media_capabilities_marks_nvme_and_bitlocker():
    disks = build_media_capabilities(
        [
            {
                "Number": 0,
                "FriendlyName": "NVMe",
                "BusType": "NVMe",
                "MediaType": "SSD",
                "IsBoot": True,
                "Partitions": [
                    {
                        "DriveLetter": "C",
                        "BitLocker": {"ProtectionStatus": "On"},
                    },
                ],
            },
        ],
    )

    disk = disks[0]
    mapping = media_by_drive_letter(disks)

    assert disk.supports_crypto_erase is True
    assert disk.is_bitlocker_protected is True
    assert mapping["C"].friendly_name == "NVMe"
