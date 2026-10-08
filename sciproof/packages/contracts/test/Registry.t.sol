// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import '../src/SciProofRegistry.sol';
contract UnauthorizedCaller {
    function callRegistry(SciProofRegistry r) external {r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),8000,1);}
}
interface Vm { function expectEmit(bool,bool,bool,bool,address) external; }
contract RegistryTest {
    Vm constant vm=Vm(address(uint160(uint256(keccak256('hevm cheat code')))));
    event Attested(bytes32 indexed researchId,bytes32 indexed versionId,bytes32 provenance,address researcher);
    function testEventEmission() public {
        SciProofRegistry r=new SciProofRegistry(address(this));
        vm.expectEmit(true,true,false,true,address(r));
        emit Attested(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),address(this));
        inputs(r);
    }
    function testZeroProvenance() public {
        SciProofRegistry r=new SciProofRegistry(address(this));
        try r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(0),bytes32(uint256(4)),address(this),8000,1){revert('zero provenance accepted');}catch{}
    }
    function testMultipleVersionsAndResearchers() public {
        SciProofRegistry r=new SciProofRegistry(address(this));inputs(r);
        r.attest(bytes32(uint256(1)),bytes32(uint256(5)),bytes32(uint256(6)),bytes32(uint256(7)),address(0xBEEF),6000,3);
        (bytes32 p1,,address a1,,,)=r.records(keccak256(abi.encode(bytes32(uint256(1)),bytes32(uint256(2)))));
        (bytes32 p2,,address a2,,,)=r.records(keccak256(abi.encode(bytes32(uint256(1)),bytes32(uint256(5)))));
        require(p1==bytes32(uint256(3)) && a1==address(this));require(p2==bytes32(uint256(6)) && a2==address(0xBEEF));
    }
    function testImmutabilityAllFields() public {
        SciProofRegistry r=new SciProofRegistry(address(this));inputs(r);
        bytes32 key=keccak256(abi.encode(bytes32(uint256(1)),bytes32(uint256(2))));
        (bytes32 p,bytes32 h,address a,uint64 t,uint16 score,uint8 status)=r.records(key);
        try r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(99)),bytes32(uint256(88)),address(0xBEEF),0,4){revert('mutation accepted');}catch{}
        (bytes32 p2,bytes32 h2,address a2,uint64 t2,uint16 score2,uint8 status2)=r.records(key);
        require(p==p2 && h==h2 && a==a2 && t==t2 && score==score2 && status==status2);
    }
    function testInvalidSummaryAndConstructor() public {
        try new SciProofRegistry(address(0)){revert('zero attestor accepted');}catch{}
        SciProofRegistry r=new SciProofRegistry(address(this));
        try r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),10001,1){revert('score accepted');}catch{}
        try r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),8000,5){revert('status accepted');}catch{}
    }

    function inputs(SciProofRegistry r) internal {r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),8000,1);}
    function testAuthorized() public {SciProofRegistry r=new SciProofRegistry(address(this)); inputs(r); (bytes32 p,,,,,)=r.records(keccak256(abi.encode(bytes32(uint256(1)),bytes32(uint256(2)))));require(p==bytes32(uint256(3)));}
    function testDuplicateRejected() public {SciProofRegistry r=new SciProofRegistry(address(this));inputs(r);try r.attest(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),8000,1){revert('duplicate allowed');}catch{}}
    function testZeroRejected() public {SciProofRegistry r=new SciProofRegistry(address(this));try r.attest(bytes32(0),bytes32(uint256(2)),bytes32(uint256(3)),bytes32(uint256(4)),address(this),8000,1){revert('zero allowed');}catch{}}
    function testUnauthorized() public {SciProofRegistry r=new SciProofRegistry(address(this));UnauthorizedCaller c=new UnauthorizedCaller();try c.callRegistry(r){revert('unauthorized allowed');}catch{}}
}
