(() => {
    const url = new URL(window.location.href)
    const pathname = url.pathname.replace(/\/+$/, '')
    const projectBase = pathname.replace(/\/verify-success\.html$/, '')
    const redirectTo = `${window.location.origin}${projectBase}/verify-success.html`
    const token = url.searchParams.get('token')
    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const type = url.searchParams.get('type') || hashParams.get('type') || 'invite'
    const hasSession = window.location.hash.includes('access_token=')

    const title = document.getElementById('title')
    const description = document.getElementById('description')
    const secondary = document.getElementById('secondary')
    const details = document.getElementById('details')
    const muted = document.getElementById('muted')
    const icon = document.getElementById('icon')

    const UI_MESSAGES = {
        'invite': {
            loadingTitle: 'Confirmando seu convite...',
            loadingDesc: 'Estamos validando o link de acesso.',
            successTitle: 'Convite aceito com sucesso!',
            successDesc: 'Sua conta foi confirmada e o acesso ao projeto foi liberado.',
            successSecondary: 'Você pode fechar esta página e fazer login no sistema.'
        },
        'magiclink': {
            loadingTitle: 'Autenticando Magic Link...',
            loadingDesc: 'Estamos validando seu link de acesso seguro.',
            successTitle: 'Login realizado com sucesso!',
            successDesc: 'Sua sessão foi autenticada de forma segura.',
            successSecondary: 'Você pode retornar ao aplicativo.'
        },
        'signup': {
            loadingTitle: 'Confirmando seu cadastro...',
            loadingDesc: 'Estamos validando seu e-mail.',
            successTitle: 'Conta ativada com sucesso!',
            successDesc: 'Seu e-mail foi confirmado e sua conta já está pronta.',
            successSecondary: 'Agora você pode fazer login no sistema.'
        },
        'email_change': {
            loadingTitle: 'Confirmando troca de e-mail...',
            loadingDesc: 'Estamos validando a alteração solicitada.',
            successTitle: 'E-mail alterado!',
            successDesc: 'Seu novo e-mail foi confirmado com sucesso.',
            successSecondary: 'Use suas novas credenciais para acessar.'
        }
    }

    const messages = UI_MESSAGES[type] || UI_MESSAGES['invite']

    if (hasSession) {
        title.textContent = messages.successTitle
        description.textContent = messages.successDesc
        secondary.textContent = messages.successSecondary
        details.classList.remove('hidden')
        muted.textContent = 'Sessão criada com sucesso.'
        return
    }

    if (token) {
        title.textContent = messages.loadingTitle
        description.textContent = messages.loadingDesc
        
        const verifyUrl = new URL(`${window.location.origin}${projectBase}/auth/v1/verify`)
        verifyUrl.searchParams.set('token', token)
        verifyUrl.searchParams.set('type', type)
        verifyUrl.searchParams.set('redirect_to', redirectTo)
        window.location.replace(verifyUrl.toString())
        return
    }

    icon.classList.add('error-icon')
    title.textContent = 'Link inválido ou incompleto'
    description.textContent = 'Não foi possível localizar os dados necessários para confirmar o acesso.'
    secondary.textContent = 'Abra novamente o link a partir do e-mail.'
    muted.textContent = 'Se o problema continuar, solicite um novo link.'
})()
