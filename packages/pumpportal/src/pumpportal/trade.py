import os
import httpx

PUMP_API_KEY = os.getenv("PUMP_API_KEY")
PUMP_PORTAL = f"https://pumpportal.fun/api/trade?api-key={PUMP_API_KEY}"


class PumpPortalError(Exception):
    pass


async def buy_tokens(
    mint, sol_amount=0.001, pool="auto", slippage=20, priorityFee=0.00005, timeout=5
):
    data = {
        "action": "buy",
        "mint": mint,
        "amount": sol_amount,
        "denominatedInSol": "true",
        "slippage": slippage,
        "priorityFee": priorityFee,
        "pool": pool,
    }
    try:
        async with httpx.AsyncClient() as session:
            response = await session.post(PUMP_PORTAL, data=data, timeout=timeout)
            if response.status_code != 200:
                print(f"❌ Error en la respuesta: {response.status_code}")
                return None
            try:
                result = response.json()
            except ValueError:
                # except aiohttp.ContentTypeError:
                print("❌ La respuesta no es JSON válida.")
                return None

            if "errors" in result and len(result["errors"]) > 0:
                print("⚠️ Error en la API:", result["errors"])
                return None

            print("✅ Trade exitoso. Transacción:", result.get("signature", result))
            return result
    except httpx.TimeoutException:
        # except asyncio.TimeoutError:
        print("⏱️ Error de tiempo de espera en compra.")
    except httpx.RequestError as e:
        # except aiohttp.ClientError as e:
        print(f"🌐 Error de red en compra: {str(e)}")

    return None


async def sell_tokens(
    mint, amount="100%", pool="auto", slippage=40, priorityFee=0.00005, timeout=5
):
    data = {
        "action": "sell",
        "mint": mint,
        "amount": amount,
        "denominatedInSol": "false",
        "slippage": slippage,
        "priorityFee": priorityFee,
        "pool": pool,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(PUMP_PORTAL, data=data)

            if response.status_code != 200:
                print(f"❌ Error en la respuesta: {response.status_code}")
                return None

            try:
                result = response.json()
            except ValueError:
                print("❌ La respuesta no es JSON válida.")
                return None

            if "errors" in result and len(result["errors"]) > 0:
                print("⚠️ Error en la API:", result["errors"])
                raise PumpPortalError(result["errors"])

            print("✅ Trade exitoso. Transacción:", result.get("tx", result))
            return result

    except httpx.TimeoutException:
        print("⏱️ Error de tiempo de espera en venta.")
    except httpx.RequestError as e:
        print(f"🌐 Error de red en venta: {str(e)}")

    return None
