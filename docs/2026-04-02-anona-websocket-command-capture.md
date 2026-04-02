# Anona websocket command capture (2026-04-02)

This note captures the native macOS app's websocket lock and unlock traffic for `Front Door Lock`.

The key result is that the app prefers local BLE when the controller is available, but it falls back to the cloud websocket command path when the macOS Bluetooth controller is powered off. Under that cloud-only condition, both `lockDoor` and `unLockDoor` are observable in the app logs with stable outbound payload hex, websocket acks, and parsed remote status pushes.

## Capture setup

- App: `/Applications/Anona Security.app`
- Lock detail screen: `Front Door Lock`
- Device ID redacted in this note as `<device_id>`
- Bluetooth controller forced off through macOS System Settings, verified by `system_profiler SPBluetoothDataType` reporting `State: Off`
- Log capture source: `/usr/bin/log stream --style compact --level debug --predicate 'process == "Anona"'`

Important behavioral finding:

- With Bluetooth on, the app sends commands to the local peripheral `MatterLock` over BLE and logs `MaiBleTransmitUtils+Lock.swift` / `MaiBleTransmitDataManager+Lock.swift`.
- With Bluetooth off, the same UI gestures use the websocket path instead.

## Websocket bootstrap

The websocket reconnect that preceded the cloud-only command run produced the expected bootstrap sequence:

```text
2026-04-02 04:09:19.217 ... PubWebSocketManager.swift[208] getWebSockInfo ---
2026-04-02 04:09:19.929 ... PubWebSocketManager.swift[215] getWebSockInfo --- response
  websocketAddress = "wss://websocketforappv2.anonasecurity.com:10006/websocket"
  websocketAesKey = <redacted>
  websocketToken = <redacted>
2026-04-02 04:09:21.514 ... MaiWebSocketManager.swift[187] sendHandMsg ----- {"operateId":"1775128161513","ts":1775128161513,"handshakeToken":"<redacted>"}
2026-04-02 04:09:21.629 ... PubWebSocketManager.swift[241] websocketConnectSuccess
2026-04-02 04:09:21.629 ... PubWebSocketManager.swift[44] connectState ----> success
```

This run did not show a separate websocket `authSync` command. The only explicit `lockAuthSync` observed in the broader session was on the BLE path.

## Lock over websocket

This exchange was captured while the lock was open and Bluetooth was off.

### Outbound command

```text
2026-04-02 04:10:12.238 ... LockWebSocketChannelDataHandler.swift[270] ----websocket lockDoor -------
2026-04-02 04:10:12.238 ... PubWebSocketManager.swift[80] websocket messageSendToDevice did = <device_id> sendID = Optional(7)
2026-04-02 04:10:12.240 ... PubWebSocketManager.swift[111] websocket sendMsg success contentStr = 083010079203062a0408abc620 did = <device_id> operateId = Optional("1775128212237501") sendID = Optional(7)
2026-04-02 04:10:12.240 ... PubWebSocketManager.swift[155] 消息发送成功 operateId = Optional("1775128212237501") did = <device_id> sendID = Optional(7)
```

### Ack frame

```text
2026-04-02 04:10:12.365 ... AppDelegate.swift[64] starScream ---- message channel --> didForm = 651A30CFC80788174800D4368DADC5DB33768539DBBE752B97BA83CDC8D2658D242F273BC6D75E2E0AF811242CB66C0A8F2E2C349815C6BD0C941E4AE051A4512DBEFBAC1F010A379640B544CE0708408BED8686
2026-04-02 04:10:12.365 ... PubWebSocketDataEntity.swift[57] 收到的数据 ---- nil ---- 1775128212237501 ------- Optional(1775128212343) ----operateId = Optional("1775128212237501") ts = Optional(1775128212343) deviceId = nil source = nil target = nil ackCode = Optional(200) isAck = Optional(true)
```

### Command success and remote push

```text
2026-04-02 04:10:15.707 ... PubWebSocketManager.swift[323] 发送的数据返回了 operateId = 1775128212237501
2026-04-02 04:10:15.707 ... LockWebSocketChannelDataHandler.swift[28] ----websocket lockWebSocketSendData success -------
2026-04-02 04:10:15.708 ... LockWebSocketChannelDataHandler.swift[277] lockDoor ---Optional("{}")
2026-04-02 04:10:15.877 ... AppDelegate.swift[64] starScream ---- message channel --> didForm = 8E69C785049F3B895BFB6E4193C07C63C519F787993FE4BEBEE9B2BB658380DAEB3C9EF9D5A19931E8B1BD640C1A1CB2B4A9FAF10A3804E53E4F7603997DF2CFE53E18458E77004037BF144DA69E743EB4DC597E28102A6E4DC7E2800149B9FA70D7E140F38171D9A78E4EFCB2FE288535C9CD69561A151D9D3418C89067FE469A5757B4D8DC4F88C350829717B3B67C52CD9DA47F1D1E8484DD74CB18C934691434790129E4BE1FCAD2D4F617CFB8D56D97B301C58479C2916FF08B5BB4E017C2A3F372A89DA5A050253EE304F1AE982235FA8ABADEB506408FAE46E19CD28193E533F1EF2C75ABC944BBF35FA6FC0F21080506D8731562EBE3D03528D3EC52BF0B382BD2C159CE99CBE7007F388906C3BD44788077987FE5056D1A6C123BFE6D29E106D40515950C6B59E86E5ADC369A8772CB786FB8A81C904C5AF88CB5653C61CD80
2026-04-02 04:10:15.878 ... PubWebSocketDataEntity.swift[57] 收到的数据 ---- <device_id> ---- 14d858ec-ce64-44b9-b242-cd29c3f4d8af ------- Optional(1775128215789) ----operateId = Optional("14d858ec-ce64-44b9-b242-cd29c3f4d8af") ts = Optional(1775128215789) deviceId = Optional("<device_id>") source = Optional(2) target = nil ackCode = nil isAck = nil
2026-04-02 04:10:15.878 ... LockWebSocketManager.swift[61] -- LockWebSocketManager --- WebsocketReciveData ---- DoorLock.DoorLockSmartPacket:
type: DOOR_LOCK
id: 3
door_lock {
  doorlock_status {
    lock_state: STATE_CLOSE
    door_state: STATE_CLOSE
```

## Unlock over websocket

This exchange was captured immediately after the lock run above, again with Bluetooth off.

### Outbound command

```text
2026-04-02 04:10:51.754 ... LockWebSocketChannelDataHandler.swift[296] ----websocket unLockDoor -------
2026-04-02 04:10:51.754 ... PubWebSocketManager.swift[80] websocket messageSendToDevice did = <device_id> sendID = Optional(6)
2026-04-02 04:10:51.756 ... PubWebSocketManager.swift[111] websocket sendMsg success contentStr = 083010069203062a0408abc620 did = <device_id> operateId = Optional("1775128251753870") sendID = Optional(6)
2026-04-02 04:10:51.756 ... PubWebSocketManager.swift[155] 消息发送成功 operateId = Optional("1775128251753870") did = <device_id> sendID = Optional(6)
```

### Ack frame

```text
2026-04-02 04:10:51.884 ... AppDelegate.swift[64] starScream ---- message channel --> didForm = 651A30CFC80788174800D4368DADC5DB33768539DBBE752B97BA83CDC8D2658D242F273BC6D75E2E0AF811242CB66C0A37D8533465B7D59DAAF2807F7496DBC4F92C05B281A0FD2C8F7CEC374E14B62A6F050484
2026-04-02 04:10:51.885 ... PubWebSocketDataEntity.swift[57] 收到的数据 ---- nil ---- 1775128251753870 ------- Optional(1775128251865) ----operateId = Optional("1775128251753870") ts = Optional(1775128251865) deviceId = nil source = nil target = nil ackCode = Optional(200) isAck = Optional(true)
```

### Command success and remote push

```text
2026-04-02 04:10:54.826 ... PubWebSocketManager.swift[323] 发送的数据返回了 operateId = 1775128251753870
2026-04-02 04:10:54.826 ... LockWebSocketChannelDataHandler.swift[28] ----websocket lockWebSocketSendData success -------
2026-04-02 04:10:54.826 ... LockWebSocketChannelDataHandler.swift[303] unLockDoor ---Optional("{}")
2026-04-02 04:10:55.040 ... AppDelegate.swift[64] starScream ---- message channel --> didForm = 8E69C785049F3B895BFB6E4193C07C63C519F787993FE4BEBEE9B2BB658380DAFD4CAB5FA1C55142FD4B4255B04190B78F0A09EE0A082670C2BD7D346006FAA671C88C1DCE0C3F83E813350DBE9BF0403F22CB581780F1686ADF4BA28A26AC15AD312E083EB2C9604D249AC16D166DC55AE3E3237CADDAEECEFD19A15176F0C24119B09ED894CBE0B047127E71B67F849B803F3901D5E19D8D1DF3952FE3A87227DD0043D1FEFCC45FC522B5D36836E643A893C9CE195DB61F8F683DAB26CAD201B7C80975CADF2A83935E23BD6359273D85F35292867ED3790DD2C244991EF510C4D7FC83D1A1DEF572408D4E6AC020AEC04550F1EAE166EEF17F6B9A04094E2AEAC97929FC82B260E81997D8D2AF24D79465DAF20EEFD15601BE1FA590EC9E0B39997A32E1F3B34543F95E93E66365A105C3D8BC463C0F5BFF0DDB6233C57B5FA1C545
2026-04-02 04:10:55.041 ... PubWebSocketDataEntity.swift[57] 收到的数据 ---- <device_id> ---- 387313cc-a9f5-48e4-ab67-4d1c2ea1fa28 ------- Optional(1775128255010) ----operateId = Optional("387313cc-a9f5-48e4-ab67-4d1c2ea1fa28") ts = Optional(1775128255010) deviceId = Optional("<device_id>") source = Optional(2) target = nil ackCode = nil isAck = nil
2026-04-02 04:10:55.041 ... LockWebSocketManager.swift[61] -- LockWebSocketManager --- WebsocketReciveData ---- DoorLock.DoorLockSmartPacket:
type: DOOR_LOCK
id: 3
door_lock {
  doorlock_status {
    lock_state: STATE_OPEN
    door_state: STATE_CLOSE
```

## Immediate implementation value

- `sendID = 7` maps to `lockDoor`
- `sendID = 6` maps to `unLockDoor`
- The outbound protobuf hex is currently:
  - lock: `083010079203062a0408abc620`
  - unlock: `083010069203062a0408abc620`
- The app expects:
  - a websocket-level ack with `ackCode = 200` and the same `operateId`
  - a follow-up command result on the same `operateId` with `lockDoor ---Optional("{}")` or `unLockDoor ---Optional("{}")`
  - a remote push carrying updated lock status in a parsed `DoorLockSmartPacket`

## Remaining uncertainty

- This capture proves the cloud command transport and gives the exact lock/unlock payload hex for one lock model, but it does not yet explain how the app derives those protobuf bytes.
- The only explicit `authSync` in the observed session was BLE-specific. If the Home Assistant command implementation can reuse the websocket bootstrap plus the captured command packets, this note is enough to proceed. If per-device websocket auth still exists elsewhere, it was not emitted in this cloud-only run.
