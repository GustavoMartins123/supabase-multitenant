(() => {
    const url = new URL(window.location.href)
    const pathname = url.pathname.replace(/\/+$/, '')
    const projectBase = pathname.replace(/\/verify-success\.html$/, '')
    const redirectTo = `${window.location.origin}${projectBase}/verify-success.html`
    const token = url.searchParams.get('token')
    const type = url.searchParams.get('type') || 'invite'
    const hasSession = window.location.hash.includes('access_token=')

    const title = document.getElementById('title')
    const description = document.getElementById('description')
    const secondary = document.getElementById('secondary')
    const details = document.getElementById('details')
    const muted = document.getElementById('muted')
    const icon = document.getElementById('icon')

    if (hasSession) {
        title.textContent = 'Convite aceito com sucesso!'
        description.textContent = 'Sua conta foi confirmada e o acesso ao projeto foi liberado.'
        secondary.textContent = 'Você pode fechar esta página e fazer login no sistema.'
        details.classList.remove('hidden')
        muted.textContent = 'Sessão criada com sucesso.'
        return
    }

    if (token) {
        const verifyUrl = new URL(`${window.location.origin}${projectBase}/auth/v1/verify`)
        verifyUrl.searchParams.set('token', token)
        verifyUrl.searchParams.set('type', type)
        verifyUrl.searchParams.set('redirect_to', redirectTo)
        window.location.replace(verifyUrl.toString())
        return
    }

    icon.classList.add('error-icon')
    title.textContent = 'Link inválido ou incompleto'
    description.textContent = 'Não foi possível localizar os dados necessários para confirmar o convite.'
    secondary.textContent = 'Abra novamente o convite a partir do e-mail.'
    muted.textContent = 'Se o problema continuar, gere um novo convite.'
})()
