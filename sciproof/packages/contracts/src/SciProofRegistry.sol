// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
contract SciProofRegistry {
    address public immutable attestor;
    struct Record {bytes32 provenance; bytes32 artifactHash; address researcher; uint64 timestamp; uint16 score; uint8 status;}
    mapping(bytes32=>Record) public records;
    event Attested(bytes32 indexed researchId,bytes32 indexed versionId,bytes32 provenance,address researcher);
    constructor(address authorized){require(authorized!=address(0),'zero attestor');attestor=authorized;}
    function attest(bytes32 researchId,bytes32 versionId,bytes32 provenance,bytes32 artifactHash,address researcher,uint16 score,uint8 status) external {
        require(msg.sender==attestor,'unauthorized');
        require(researchId!=0 && versionId!=0 && provenance!=0 && artifactHash!=0 && researcher!=address(0),'zero input');
        require(score<=10000 && status<=4,'invalid summary');
        bytes32 key=keccak256(abi.encode(researchId,versionId));
        require(records[key].researcher==address(0),'immutable version');
        records[key]=Record(provenance,artifactHash,researcher,uint64(block.timestamp),score,status);
        emit Attested(researchId,versionId,provenance,researcher);
    }
}
