;;; lsp-sqls.el --- SQL Client settings -*- lexical-binding: t; -*-

;; Copyright (C) 2023 Chahak Mehta

;; Author: Chahak Mehta
;; Keywords: sql lsp

;; This program is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation, either version 3 of the License, or
;; (at your option) any later version.

;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with this program.  If not, see <https://www.gnu.org/licenses/>.

;;; Commentary:

;; LSP client for SQL

;;; Code:

(require 'lsp-mode)

(defgroup lsp-sql-ls nil
  "LSP support for SQL, using sql-ls."
  :group 'lsp-mode
  :link '(url-link "https://github.com/chahak13/sql-lsp")
  :package-version `(lsp-mode . "7.0"))

(defcustom lsp-sql-ls-server "sql-ls"
  "Path to the `sql-ls` binary."
  :group 'lsp-sql-ls
  :risky t
  :type 'file
  :package-version `(lsp-mode . "7.0"))

(defcustom lsp-sql-ls-workspace-config-path "workspace"
  "If non-nil then setup workspace configuration with json file path."
  :group 'lsp-sql-ls
  :risky t
  :type '(choice (const "workspace")
          (const "root"))
  :package-version `(lsp-mode . "7.0"))

(defun lsp-sql-ls--make-launch-cmd ()
  (-let [base `(,lsp-sql-ls-server)]
    ;; we can add some options to command. (e.g. "-config")
    base))


(defcustom lsp-sql-ls-timeout 0.5
  "Timeout to use for `sql-ls' requests."
  :type 'number
  :package-version '(lsp-mode . "8.0.0"))

(defcustom lsp-sql-ls-connections nil
  "The connections to the SQL server(s)."
  :type '(repeat (alist :key-type (choice
                                   (const :tag "Driver" driver)
                                   (const :tag "Connection String" dataSourceName))
                        :value-type string)))

(defun lsp-sql-ls-setup-workspace-configuration ()
  "Setup workspace configuration using json file.
Depending on `lsp-sql-ls-workspace-config-path'."

  (if lsp-sql-ls-connections
      (lsp--set-configuration `(:sql-ls (:connections ,(apply #'vector lsp-sql-ls-connections))))
    (when-let ((config-json-path (cond
                                  ((equal lsp-sql-ls-workspace-config-path "workspace")
                                   ".sql-ls/config.json")
                                  ((equal lsp-sql-ls-workspace-config-path "root")
                                   (-> (lsp-workspace-root)
                                       (f-join ".sql-ls/config.json"))))))
      (when (file-exists-p config-json-path)
        (lsp--set-configuration (lsp--read-json-file config-json-path))))))

(defun lsp-sql-ls--show-results (result)
  "Show RESULT of query execution in a buffer."
  (with-current-buffer (get-buffer-create "*sql-ls results*")
    (with-help-window (buffer-name)
      (erase-buffer)
      (insert result))))

(defun lsp-sql-ls-execute-query (&optional command start end)
  "Execute COMMAND on buffer text against current database.
Buffer text is between START and END.  If START and END are nil,
use the current region if set, otherwise the entire buffer."
  (interactive)
  (lsp-sql-ls--show-results
   (lsp-request
    "workspace/executeCommand"
    (list :command "executeQuery"
          :arguments (or
                      (when command
                        (lsp:command-arguments? command))
                      (vector (lsp--buffer-uri)))
          :timeout lsp-sql-ls-timeout
          :range (list
                  :start (lsp--point-to-position
                          (cond
                           (start start)
                           ((use-region-p) (region-beginning))
                           (t (point-min))))
                  :end (lsp--point-to-position
                        (cond
                         (end end)
                         ((use-region-p) (region-end))
                         (t (point-max)))))))))

(defun lsp-sql-ls-explain-query (&optional command start end)
  "Explain COMMAND on buffer text against current database.
Buffer text is between START and END.  If START and END are nil,
use the current region if set, otherwise the entire buffer."
  (interactive)
  (lsp-sql-ls--show-results
   (lsp-request
    "workspace/executeCommand"
    (list :command "explainQuery"
          :arguments (or
                      (when command
                        (lsp:command-arguments? command))
                      (vector (lsp--buffer-uri)))
          :timeout lsp-sql-ls-timeout
          :range (list
                  :start (lsp--point-to-position
                          (cond
                           (start start)
                           ((use-region-p) (region-beginning))
                           (t (point-min))))
                  :end (lsp--point-to-position
                        (cond
                         (end end)
                         ((use-region-p) (region-end))
                         (t (point-max)))))))))

(defun lsp-sql-ls-execute-paragraph (&optional command)
  "Execute COMMAND on paragraph against current database."
  (interactive)
  (let ((start (save-excursion (backward-paragraph) (point)))
        (end (save-excursion (forward-paragraph) (point))))
    (lsp-sql-ls-execute-query command start end)))

(defun lsp-sql-ls-show-databases (&optional _command)
  "Show databases."
  (interactive)
  (lsp-sql-ls--show-results
   (lsp-request
    "workspace/executeCommand"
    (list :command "showDatabases" :timeout lsp-sql-ls-timeout))))

(defun lsp-sql-ls-show-schemas (&optional _command)
  "Show schemas."
  (interactive)
  (lsp-sql-ls--show-results
   (lsp-request
    "workspace/executeCommand"
    (list :command "showSchemas" :timeout lsp-sql-ls-timeout))))

(defun lsp-sql-ls-show-connections (&optional _command)
  "Show connections."
  (interactive)
  (lsp-sql-ls--show-results
   (lsp-request
    "workspace/executeCommand"
    (list :command "showConnections" :timeout lsp-sql-ls-timeout))))

(defun lsp-sql-ls-switch-database (&optional _command)
  "Switch database."
  (interactive)
  (lsp-workspace-command-execute
   "switchDatabase"
   (vector (completing-read
            "Select database: "
            (s-lines (lsp-workspace-command-execute "showDatabases"))
            nil
            t))))

(defun lsp-sql-ls-switch-connection (&optional _command)
  "Switch connection."
  (interactive)
  (lsp-workspace-command-execute
   "switchConnections"
   (vector
    (completing-read
     "Select connection: "
     (s-lines (lsp-workspace-command-execute  "showConnectionAliases"))
     nil
     t))))

(lsp-register-client
 (make-lsp-client :new-connection (lsp-stdio-connection #'lsp-sql-ls--make-launch-cmd)
                  :major-modes '(sql-mode)
                  :priority -1
                  :action-handlers (ht ("executeParagraph" #'lsp-sql-ls-execute-paragraph)
                                       ("explainQuery" #'lsp-sql-ls-explain-query)
                                       ("executeQuery" #'lsp-sql-ls-execute-query)
                                       ("showDatabases" #'lsp-sql-ls-show-databases)
                                       ("showSchemas" #'lsp-sql-ls-show-schemas)
                                       ("showConnections" #'lsp-sql-ls-show-connections)
                                       ("switchDatabase" #'lsp-sql-ls-switch-database)
                                       ("switchConnections" #'lsp-sql-ls-switch-connection))
                  :server-id 'sql-ls
                  :initialized-fn (lambda (workspace)
                                    (-> workspace
                                        (lsp--workspace-server-capabilities)
                                        (lsp:set-server-capabilities-execute-command-provider? t))
                                    (with-lsp-workspace workspace
                                      (lsp-sql-ls-setup-workspace-configuration)))))

(lsp-consistency-check lsp-sql-ls)

(provide 'lsp-sql-ls)
;;; lsp-sql-ls.el ends here
