#!/usr/bin/env python3
"""
Test script to verify LLM services (Ollama and LM Studio) integration
"""
import asyncio
import httpx
import json
from typing import Dict, List, Any


async def test_ollama_service(url: str) -> Dict[str, Any]:
    """Test Ollama service endpoints"""
    print(f"\n🔍 Testing Ollama service at {url}")
    results = {"url": url, "type": "ollama", "tests": {}}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test 1: List models
        try:
            response = await client.get(f"{url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                results["tests"]["list_models"] = {"success": True, "models": models}
                print(f"✅ Found {len(models)} models: {', '.join(models[:3])}...")
            else:
                results["tests"]["list_models"] = {"success": False, "error": f"Status {response.status_code}"}
                print(f"❌ Failed to list models: Status {response.status_code}")
        except Exception as e:
            results["tests"]["list_models"] = {"success": False, "error": str(e)}
            print(f"❌ Failed to list models: {e}")
        
        # Test 2: Chat completion
        try:
            payload = {
                "model": "qwen2.5:32b-instruct",
                "messages": [{"role": "user", "content": "Say 'Hello from Ollama' in 5 words or less"}],
                "stream": False
            }
            response = await client.post(f"{url}/api/chat", json=payload)
            if response.status_code == 200:
                data = response.json()
                results["tests"]["chat_completion"] = {"success": True, "response": data}
                print(f"✅ Chat completion successful")
            else:
                results["tests"]["chat_completion"] = {"success": False, "error": f"Status {response.status_code}"}
                print(f"❌ Chat completion failed: Status {response.status_code}")
        except Exception as e:
            results["tests"]["chat_completion"] = {"success": False, "error": str(e)}
            print(f"❌ Chat completion failed: {e}")
    
    return results


async def test_lmstudio_service(url: str) -> Dict[str, Any]:
    """Test LM Studio service endpoints (OpenAI-compatible)"""
    print(f"\n🔍 Testing LM Studio service at {url}")
    results = {"url": url, "type": "lmstudio", "tests": {}}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test 1: List models
        try:
            response = await client.get(f"{url}/v1/models")
            if response.status_code == 200:
                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                results["tests"]["list_models"] = {"success": True, "models": models}
                print(f"✅ Found {len(models)} models: {', '.join(models[:3])}...")
            else:
                results["tests"]["list_models"] = {"success": False, "error": f"Status {response.status_code}"}
                print(f"❌ Failed to list models: Status {response.status_code}")
        except Exception as e:
            results["tests"]["list_models"] = {"success": False, "error": str(e)}
            print(f"❌ Failed to list models: {e}")
        
        # Test 2: Chat completion
        try:
            payload = {
                "model": "qwen/qwen3-30b-a3b",
                "messages": [{"role": "user", "content": "Say 'Hello from LM Studio' in 5 words or less"}],
                "stream": False
            }
            response = await client.post(f"{url}/v1/chat/completions", json=payload)
            if response.status_code == 200:
                data = response.json()
                results["tests"]["chat_completion"] = {"success": True, "response": data}
                print(f"✅ Chat completion successful")
                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    print(f"   Response: {content}")
            else:
                error_text = response.text
                results["tests"]["chat_completion"] = {"success": False, "error": f"Status {response.status_code}: {error_text}"}
                print(f"❌ Chat completion failed: Status {response.status_code}")
                print(f"   Error: {error_text}")
        except Exception as e:
            results["tests"]["chat_completion"] = {"success": False, "error": str(e)}
            print(f"❌ Chat completion failed: {e}")
    
    return results


async def main():
    """Main test function"""
    print("🚀 Testing LLM Services for DharasLocalAI")
    print("=" * 50)
    
    # Services to test
    services = [
        {"name": "LMStudio_Service", "type": "lmstudio", "url": "http://your-lmstudio-host:1234"},
        {"name": "Ollama_Service", "type": "ollama", "url": "http://your-ollama-host:11434"}
    ]
    
    results = []
    
    for service in services:
        if service["type"] == "ollama":
            result = await test_ollama_service(service["url"])
        elif service["type"] == "lmstudio":
            result = await test_lmstudio_service(service["url"])
        else:
            print(f"❓ Unknown service type: {service['type']}")
            continue
        
        result["name"] = service["name"]
        results.append(result)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    for result in results:
        print(f"\n{result['name']} ({result['type']}):")
        for test_name, test_result in result["tests"].items():
            status = "✅" if test_result.get("success") else "❌"
            print(f"  {status} {test_name}")
            if not test_result.get("success"):
                print(f"     Error: {test_result.get('error')}")
    
    # Save results
    with open("llm_services_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Detailed results saved to llm_services_test_results.json")


if __name__ == "__main__":
    asyncio.run(main())