from fastapi import APIRouter, UploadFile
from arbiter.controllers.processdata import receiveLoanApplicationFromFile, get_application as getApp, get_decision as getDec, get_decision_for_application as getDecisionForApp, is_loan_accepted as isLoanAccepted, loadFileForRAG, searchRAG, retrieveForDecision
router = APIRouter(prefix="/route")

@router.post("/load_file")
async def load_file_for_RAG(file: UploadFile):
    return await loadFileForRAG(file)


@router.post('/search_rag')
async def search_rag(input: str, mode: str = "semantic", limit: int = 3):
    return await searchRAG(input, mode, limit)


@router.get('/retrieve_for_decision')
async def retrieve_for_decision(application_id: int, k: int = 3):
    return await retrieveForDecision(application_id, k)


@router.post('/loan_application')
async def loan_application(file: UploadFile):
    return await receiveLoanApplicationFromFile(file)


@router.get('/get_application')
async def get_application(item_id: int):
    data = await getApp(item_id)
    return data

@router.get('/get_decision')
async def get_decision(item_id: int):
    data = await getDec(item_id)
    return data

@router.get('/get_decision_for_application')
async def get_decision_for_application(application_id: int):
    return await getDecisionForApp(application_id)

@router.get('/is_loan_accepted')
async def is_loan_accepted(application_id: int):
    return await isLoanAccepted(application_id)
