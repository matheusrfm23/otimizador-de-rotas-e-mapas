# lembrete_commit_v2.py
# Um script para lembrar ou automatizar commits e pushes em um repositório Git.
# VERSÃO 2.0: Adicionado modo automático para commits e pushes periódicos.

import time
import os
import subprocess
import tkinter as tk
from tkinter import ttk
from datetime import datetime

# ==============================================================================
# SEÇÃO 1: UTILITÁRIOS E FUNÇÕES GIT
# ==============================================================================

def is_git_repo():
    """Verifica se o diretório atual é um repositório Git."""
    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode == 0 and result.stdout.strip() == "true"

def get_modified_files():
    """Retorna uma lista de arquivos modificados, adicionados ou renomeados."""
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    files = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Extrai o nome do arquivo, lidando com renomeações
        name = line[3:]
        if "->" in name:
            name = name.split("->", 1)[1].strip()
        files.append(name)
    return files

def git_add_commit(message):
    """Adiciona todos os arquivos e faz um commit."""
    subprocess.run(["git", "add", "-A"], creationflags=subprocess.CREATE_NO_WINDOW)
    commit_result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    # Retorna True se o commit foi bem-sucedido (ou seja, havia algo para commitar)
    return "nothing to commit" not in commit_result.stdout and commit_result.returncode == 0

def git_push():
    """Faz push para o 'origin'."""
    branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"

    remote_result = subprocess.run(["git", "remote"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if "origin" not in remote_result.stdout.splitlines():
        return False, "remote 'origin' não encontrado"

    # Verifica se o branch remoto (upstream) está configurado
    upstream_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if upstream_result.returncode == 0:
        push_command = ["git", "push"]
    else:
        push_command = ["git", "push", "-u", "origin", branch]

    push_result = subprocess.run(push_command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return push_result.returncode == 0, push_result.stderr.strip()

def write_log(log_path, lines):
    """Escreve uma entrada no arquivo de log."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n" + ("-" * 60) + "\n")
    except Exception as e:
        print(f"Erro ao escrever no log: {e}")

def play_sound(root):
    """Toca um som de notificação."""
    try:
        root.bell() # Som padrão do sistema
    except Exception:
        pass

# ==============================================================================
# SEÇÃO 2: JANELA DE POP-UP (MODO INTERATIVO)
# ==============================================================================

def popup_commit_window(interval_min, session_str, files):
    """Cria e exibe a janela de pop-up para o modo interativo."""
    result = {"commit": False, "push": False, "action": "ignorar"}

    root = tk.Tk()
    root.title("Lembrete de Commit")
    root.geometry("480x380")
    root.resizable(False, False)
    root.attributes("-topmost", True) # Mantém a janela no topo

    play_sound(root)

    # --- Widgets ---
    main_frame = ttk.Frame(root, padding="10")
    main_frame.pack(fill="both", expand=True)

    info_label = ttk.Label(main_frame, text=f"Passaram-se {interval_min} minutos.\nTempo de sessão: {session_str}", justify="left")
    info_label.pack(pady=5, anchor="w")

    ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=5)

    files_header_label = ttk.Label(main_frame, text="Arquivos alterados:", justify="left", font=("Segoe UI", 9, "bold"))
    files_header_label.pack(anchor="w")

    # Área de texto com scroll para os arquivos
    text_frame = ttk.Frame(main_frame)
    text_frame.pack(fill="both", expand=True, pady=5)
    files_text = tk.Text(text_frame, height=8, wrap="word", state="disabled", background=root.cget('bg'), relief="flat")
    scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=files_text.yview)
    files_text.configure(yscrollcommand=scrollbar.set)
    
    files_text.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    files_text.configure(state="normal")
    files_text.insert("1.0", "\n".join(files) if files else "Nenhuma alteração detectada.")
    files_text.configure(state="disabled")

    # Checkboxes
    commit_var = tk.BooleanVar(value=True)
    push_var = tk.BooleanVar(value=False)
    commit_cb = ttk.Checkbutton(main_frame, text="Salvar localmente (commit)", variable=commit_var)
    push_cb = ttk.Checkbutton(main_frame, text="Enviar para o repositório remoto (push)", variable=push_var)
    commit_cb.pack(anchor="w", padx=5)
    push_cb.pack(anchor="w", padx=5)

    # --- Funções dos Botões ---
    def on_salvar():
        result["commit"] = commit_var.get()
        result["push"] = push_var.get()
        result["action"] = "salvar"
        root.destroy()

    def on_ignorar():
        result["action"] = "ignorar"
        root.destroy()

    def on_encerrar():
        result["action"] = "encerrar"
        root.destroy()

    # Botões
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(pady=15, fill="x", side="bottom")
    ttk.Button(button_frame, text="Salvar", command=on_salvar).pack(side="left", expand=True, padx=5)
    ttk.Button(button_frame, text="Ignorar", command=on_ignorar).pack(side="left", expand=True, padx=5)
    ttk.Button(button_frame, text="Encerrar", command=on_encerrar).pack(side="left", expand=True, padx=5)

    root.mainloop()
    return result

# ==============================================================================
# SEÇÃO 3: LÓGICA DOS MODOS DE EXECUÇÃO
# ==============================================================================

def run_interactive_cycle(log_path, session_start, interval_min):
    """Executa um ciclo do modo interativo (com pop-up)."""
    session_str = f"{int((time.time() - session_start) / 60)} minutos"
    files = get_modified_files()
    
    if not files:
        print(f"({datetime.now().strftime('%H:%M')}) Nenhum arquivo modificado. Aguardando próximo ciclo...")
        return True # Continua o loop

    response = popup_commit_window(interval_min, session_str, files)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if response["action"] == "encerrar":
        log_lines = [f"[{timestamp}] 🛑 Sessão encerrada pelo usuário", f"  Duração: {session_str}"]
        write_log(log_path, log_lines)
        print("🛑 Sessão encerrada pelo usuário.")
        return False # Encerra o loop

    elif response["action"] == "ignorar":
        log_lines = [f"[{timestamp}] ⏭️ Commit ignorado", f"  Duração: {session_str}", f"  Arquivos: {(', '.join(files) if files else '—')}"]
        write_log(log_path, log_lines)
        print("⏭️ Commit ignorado desta vez.")
        return True

    # Ação de Salvar
    commit_status = "não solicitado"
    if response["commit"]:
        commit_msg = f"Checkpoint automático - {timestamp}"
        if git_add_commit(commit_msg):
            commit_status = "sucesso"
            print("✅ Commit local salvo com sucesso.")
        else:
            commit_status = "nada para commitar"
            print("⚠️ Nenhuma alteração para salvar.")
    
    push_status = "não solicitado"
    if response["push"]:
        if commit_status != "sucesso":
            print("⚠️ O push só é realizado após um commit bem-sucedido neste ciclo.")
            push_status = "ignorado (sem commit)"
        else:
            ok, note = git_push()
            push_status = "sucesso" if ok else f"falhou ({note or 'erro'})"
            print(f"🚀 Push para o repositório remoto: {push_status}.")

    log_lines = [
        f"[{timestamp}] ✅ Ação de salvamento",
        f"  Duração: {session_str}",
        f"  Arquivos: {(', '.join(files) if files else '—')}",
        f"  Commit: {commit_status}",
        f"  Push: {push_status}"
    ]
    write_log(log_path, log_lines)
    return True

def run_automatic_cycle(log_path, session_start, auto_push):
    """Executa um ciclo do modo automático (sem pop-up)."""
    files = get_modified_files()
    if not files:
        print(f"({datetime.now().strftime('%H:%M')}) Nenhuma alteração detectada. Aguardando próximo ciclo...")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_str = f"{int((time.time() - session_start) / 60)} minutos"
    
    # Sempre tenta fazer o commit
    commit_msg = f"Checkpoint automático - {timestamp}"
    commit_ok = git_add_commit(commit_msg)

    if not commit_ok:
        print("⚠️ Nenhuma alteração para salvar.")
        return

    print("✅ Commit automático salvo com sucesso.")
    
    # Tenta fazer o push se habilitado
    push_status = "desabilitado"
    if auto_push:
        ok, note = git_push()
        push_status = "sucesso" if ok else f"falhou ({note or 'erro'})"
        print(f"🚀 Push para o repositório remoto: {push_status}.")

    log_lines = [
        f"[{timestamp}] ✅ Commit automático",
        f"  Duração: {session_str}",
        f"  Arquivos: {(', '.join(files) if files else '—')}",
        f"  Push: {push_status}"
    ]
    write_log(log_path, log_lines)

# ==============================================================================
# SEÇÃO 4: FUNÇÃO PRINCIPAL
# ==============================================================================

def main():
    """Ponto de entrada do script."""
    print("--- 🔔 Lembrete de Commit v2.0 ---")
    if not is_git_repo():
        print("❌ ERRO: Esta pasta não é um repositório Git. Encerrando.")
        time.sleep(5)
        return

    # --- Configuração Inicial ---
    mode = input("▶️ Modo de execução: [A]utomático ou [I]nterativo (padrão=I): ").strip().upper()
    auto_push = False
    if mode == 'A':
        print("\n🚀 MODO AUTOMÁTICO ATIVADO")
        print("O script fará commits automaticamente em segundo plano.")
        push_choice = input("  ↳ Fazer push automático a cada salvamento? [S]im/[N]ão (padrão=N): ").strip().upper()
        auto_push = (push_choice == 'S')
    else:
        print("\n팝 MODO INTERATIVO ATIVADO")
        print("O script exibirá um pop-up para lembrá-lo de fazer commit.")
        mode = 'I' # Garante o padrão

    try:
        interval_input = input("⏱️ Intervalo de lembrete em minutos (padrão=20): ").strip()
        interval_min = int(interval_input) if interval_input else 20
    except ValueError:
        interval_min = 20
    
    session_start = time.time()
    log_path = os.path.join(os.getcwd(), "commits_log.txt")
    
    print(f"\n✅ Configuração concluída. Verificando a cada {interval_min} minutos.")
    print("Pressione Ctrl+C para encerrar a qualquer momento.")
    print("-" * 35)

    # --- Loop Principal ---
    while True:
        try:
            # Aguarda o intervalo definido
            time.sleep(interval_min * 60)
            
            if mode == 'A':
                run_automatic_cycle(log_path, session_start, auto_push)
            else: # Modo Interativo
                if not run_interactive_cycle(log_path, session_start, interval_min):
                    break # Encerra se a função retornar False

        except KeyboardInterrupt:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session_str = f"{int((time.time() - session_start) / 60)} minutos"
            log_lines = [f"[{timestamp}] 🛑 Sessão encerrada (Ctrl+C)", f"  Duração: {session_str}"]
            write_log(log_path, log_lines)
            print("\n🛑 Encerrado pelo usuário (Ctrl+C).")
            break

if __name__ == "__main__":
    main()
