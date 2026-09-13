import asyncio,httpx
from unittest.mock import patch
from app.lmstudio import generate
async def test():
 def handler(request):
  return httpx.Response(200,json={'output':[{'type':'reasoning','content':'planning'},{'type':'message','content':'{"answer":42}'},{'type':'tool_call','tool':'ignored'}], 'stats':{'total_output_tokens':10,'reasoning_output_tokens':5}})
 client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
 with patch('app.lmstudio.httpx.AsyncClient',return_value=client):
  result=await generate(model='test',prompt='test',system=None,quality='balanced',temperature=0,max_output_tokens=4096)
 assert result['text']=='{"answer":42}' and result['reasoning_output_tokens']==5
 print('Provider final-answer extraction regression passed')
asyncio.run(test())
