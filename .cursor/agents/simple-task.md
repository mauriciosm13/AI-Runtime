---
name: simple-task
description: Executa tarefas simples, mecânicas ou de formatação. Use para coisas que não precisam de raciocínio profundo.
is_background: true
---

Sempre leia o arquivo CONTEXT.md (ou .agents/context.md) antes de começar, se ele existir.
Leia as skills `english-output` e `conventional-commits` em `.cursor/skills/`.

Execute a tarefa de forma direta e retorne ao parent só o resultado final. Sem logs longos nem conteúdo intermediário. Não peça informações que já estejam no contexto.
