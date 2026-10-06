"""Shared integration-test upload helper."""


def upload_session(client,video_file,options):
    value=client.post('/api/uploads',json={'filename':video_file.name,'size':video_file.stat().st_size,'options':options}).json()
    assert client.put(f"/api/uploads/{value['id']}?offset=0",content=video_file.read_bytes()).status_code==200
    response=client.post(f"/api/uploads/{value['id']}/complete")
    assert response.status_code==200
    return response.json()
