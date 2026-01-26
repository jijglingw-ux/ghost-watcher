// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract RelicProtocolV5 {
    // 定义一个遗物信托
    struct Vault {
        address creator;        // 发布人钱包
        address beneficiary;    // 受益人钱包
        uint256 lastCheckIn;    // 最后签到时间
        uint256 timeDelta;      // 超时阈值 (秒)
        string encryptedKey;    // 加密后的密钥 (IPFS Hash 或 密文)
        bool isReleased;        // 是否已释放
    }

    mapping(address => Vault) public vaults;

    event KeyReleased(address indexed creator, address indexed beneficiary, string key);
    event CheckedIn(address indexed creator, uint256 time);

    // 1. 部署信托
    function createVault(address _beneficiary, uint256 _timeDelta, string memory _encryptedKey) public {
        vaults[msg.sender] = Vault({
            creator: msg.sender,
            beneficiary: _beneficiary,
            lastCheckIn: block.timestamp,
            timeDelta: _timeDelta,
            encryptedKey: _encryptedKey,
            isReleased: false
        });
    }

    // 2. 我还活着 (Heartbeat)
    function checkIn() public {
        require(msg.sender == vaults[msg.sender].creator, "Not creator");
        vaults[msg.sender].lastCheckIn = block.timestamp;
        emit CheckedIn(msg.sender, block.timestamp);
    }

    // 3. 触发死手开关 (任何人都可以调用，只要时间到了)
    function distribute(address _creator) public {
        Vault storage v = vaults[_creator];
        require(!v.isReleased, "Already released");
        // 核心逻辑：区块链时间戳检查
        require(block.timestamp > v.lastCheckIn + v.timeDelta, "Creator is still active");

        v.isReleased = true;
        // 在链上公开“加密密钥”，此时受益人可以用自己的私钥去解密它
        emit KeyReleased(v.creator, v.beneficiary, v.encryptedKey);
    }
}
