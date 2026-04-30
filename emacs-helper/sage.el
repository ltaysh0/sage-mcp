;;; sage.el --- Knowledge base search via sage -*- lexical-binding: t; -*-
;;
;; Author: Olivia Taylor
;; Version: 0.1.0
;; Package-Requires: ((emacs "28.1") (consult "0.35") (marginalia "0.15") (transient "0.4.0"))
;; Homepage: https://github.com/livtaylor-generac/ccc.el
;; Keywords: tools, search
;;
;;; Commentary:
;;
;; Knowledge base search powered by sage-mcp, presented via consult with
;; live buffer preview and marginalia annotations.  Calls the `sage' CLI
;; directly as a subprocess — no MCP connection or Docker required.
;;
;; Entry points:
;;   `sage-search'     -- search all configured KBs
;;   `sage-search-kb'  -- search a specific KB (with completion)
;;   `sage-index'      -- index / re-index (streams output to *sage-index*)
;;   `sage-dispatch'   -- transient menu with full CLI flag control
;;
;;; Code:

(require 'cl-lib)
(require 'consult)
(require 'marginalia)
(require 'transient)

;;; Customization -------------------------------------------------------

(defgroup sage nil
  "Knowledge base search via sage."
  :group 'tools
  :prefix "sage-")

(defcustom sage-cli-command "sage"
  "Name or absolute path of the sage CLI executable."
  :type 'string
  :group 'sage)

(defcustom sage-config-file nil
  "Path to sage config.yaml, or nil to use sage's own default (CWD/config.yaml)."
  :type '(choice (const :tag "Default (CWD/config.yaml)" nil)
          (file :tag "Explicit path"))
  :group 'sage)

(defcustom sage-default-top-k 10
  "Default maximum number of search results returned by sage."
  :type 'integer
  :group 'sage)

(defcustom sage-file-name-length-limit 80
  "Maximum display length for file paths in search result candidates."
  :type 'integer
  :group 'sage)

;;; Internal state ------------------------------------------------------

(defvar sage-search-history nil
  "Minibuffer history for sage search queries.")

(defvar sage--current-candidates nil
  "Alist of (candidate-string . result-plist) for the active search session.")

(define-fringe-bitmap 'sage-range-bar
  (make-vector 40 #b00111000) nil nil '(top periodic))

;;; CLI utilities -------------------------------------------------------

(defun sage--config-args ()
  "Return (\"--config\" path) when `sage-config-file' is set, else nil."
  (when sage-config-file
    (list "--config" (expand-file-name sage-config-file))))

(defun sage--targ-get (targs prefix)
  "Return the value of the first entry in TARGS whose string begins with PREFIX.
E.g. (sage--targ-get args \"--kb=\") on \"--kb=homelab\" returns \"homelab\"."
  (when-let ((entry (cl-find-if (lambda (s) (string-prefix-p prefix s)) targs)))
    (substring entry (length prefix))))

(defun sage--run-json (subcommand args)
  "Run `sage SUBCOMMAND ARGS --json' synchronously; return parsed JSON.
The return value is a hash-table (for objects) or list (for arrays).
Signals an error if the process exits non-zero or produces no JSON."
  (let* ((full-args (append (list subcommand) args (list "--json")))
         (buf (generate-new-buffer " *sage-json*"))
         exit-code output)
    (unwind-protect
        (progn
          (setq exit-code
                (apply #'call-process sage-cli-command nil buf nil full-args))
          (setq output (with-current-buffer buf (buffer-string))))
      (kill-buffer buf))
    (unless (zerop exit-code)
      (error "Sage exited %d:\n%s" exit-code output))
    ;; sage prints "Using config: ..." to stderr now, but guard against any
    ;; stray prefix lines by locating the first line that opens a JSON value.
    (let ((json-start (or (string-search "\n{" output)
                          (string-search "\n[" output)
                          (when (or (string-prefix-p "{" output)
                                    (string-prefix-p "[" output))
                            -1))))
      (unless json-start
        (error "Sage: no JSON found in output:\n%s" output))
      (json-parse-string (substring output (1+ json-start))
                         :object-type 'hash-table
                         :array-type  'list))))

;;; KB listing ----------------------------------------------------------

(defun sage--list-kb-names ()
  "Return list of KB name strings via `sage list-kbs --json'.
Falls back to plain `read-string' on error (e.g. config not yet configured)."
  (condition-case err
      (mapcar (lambda (kb) (gethash "name" kb))
              (sage--run-json "list-kbs" (sage--config-args)))
    (error
     (message "sage--list-kb-names: %s" (error-message-string err))
     nil)))

;;; Arg builders --------------------------------------------------------

(defun sage--build-search-args (targs)
  "Build CLI args for `sage search' from TARGS plus defcustoms.
TARGS is the list from `(transient-args \\='sage-dispatch)', or
nil for defaults. Handles --filter-type= and
--filter-status= → `--filter key=value' pairs."
  (let* (;; --config: transient overrides defcustom
         (config (or (when-let (v (sage--targ-get targs "--config="))
                       (list "--config" (expand-file-name v)))
                     (sage--config-args)))
         ;; --kb
         (kb (when-let (v (sage--targ-get targs "--kb="))
               (list "--kb" v)))
         ;; --top-k: transient overrides defcustom
         (top-k (list "--top-k"
                      (or (sage--targ-get targs "--top-k=")
                          (number-to-string sage-default-top-k))))
         ;; --no-hybrid switch
         (hybrid (when (member "--no-hybrid" targs) '("--no-hybrid")))
         ;; --filter type=X
         (ftype (when-let (v (sage--targ-get targs "--filter-type="))
                  (list "--filter" (concat "type=" v))))
         ;; --filter status=X
         (fstat (when-let (v (sage--targ-get targs "--filter-status="))
                  (list "--filter" (concat "status=" v)))))
    (append config kb top-k hybrid ftype fstat)))

(defun sage--build-index-args (targs &optional kb force)
  "Build CLI arg list for `sage index' from transient TARGS.
KB and FORCE supplement or override values from TARGS."
  (let* ((config (or (when-let (v (sage--targ-get targs "--config="))
                       (list "--config" (expand-file-name v)))
                     (sage--config-args)))
         (kb-arg (or (when kb (list "--kb" kb))
                     (when-let (v (sage--targ-get targs "--kb="))
                       (list "--kb" v))))
         (force-arg (when (or force (member "--force" targs)) '("--force"))))
    (append config kb-arg force-arg)))

;;; Result display helpers ----------------------------------------------

(defun sage--result-summary (text)
  "Return the first non-blank line of TEXT, capped at 60 characters."
  (let* ((first   (car (split-string (string-trim text) "\n")))
         (trimmed (string-trim first)))
    (if (> (length trimmed) 60)
        (concat (substring trimmed 0 57) "…")
      trimmed)))

(defun sage--file-name-trim (path limit)
  "Trim PATH to LIMIT characters, keeping the tail."
  (if (> (length path) limit)
      (concat "…" (substring path (- (length path) (1- limit))))
    path))

(defun sage--create-candidate (result)
  "Return cons (display-key . result-plist) for RESULT plist."
  (let* ((file    (sage--file-name-trim (plist-get result :file)
                                        sage-file-name-length-limit))
         (summary (sage--result-summary (plist-get result :text)))
         (key     (format "%s · %s" file summary)))
    (cons key result)))

(defun sage--annotate (candidate)
  "Marginalia annotation for a sage search CANDIDATE."
  (when-let (r (cdr (assoc candidate sage--current-candidates)))
    (marginalia--fields
     ((plist-get r :kb)
      :face 'marginalia-type)
     ((format "%.3f" (plist-get r :score))
      :face 'marginalia-number)
     ((when (hash-table-p (plist-get r :metadata))
        (gethash "type" (plist-get r :metadata)))
      :face 'marginalia-documentation))))

(add-to-list 'marginalia-annotators
             '(sage-result sage--annotate builtin none))

;;; Core search ---------------------------------------------------------

(defun sage--parse-results (json)
  "Convert sage search JSON response to a list of result plists."
  (mapcar (lambda (r)
            (list :score    (gethash "score"     r)
                  :file     (gethash "file_path" r)
                  :kb       (gethash "kb"        r)
                  :text     (gethash "text"      r)
                  :metadata (gethash "metadata"  r)))
          (gethash "results" json)))

(defun sage--text-position (buf text)
  "Return a marker in BUF at the start of TEXT's first line, or nil.
Uses the first 80 characters of the first non-blank line as the needle."
  (with-current-buffer buf
    (save-excursion
      (goto-char (point-min))
      (let* ((first-line (string-trim (car (split-string (string-trim text) "\n"))))
             (needle (if (> (length first-line) 80)
                         (substring first-line 0 80)
                       first-line)))
        (when (and (not (string-empty-p needle))
                   (search-forward needle nil t))
          (point-marker))))))

(defun sage--do-search (query args)
  "Run `sage search QUERY ARGS' and present results interactively via consult."
  (let* ((json    (sage--run-json "search" (cons query args)))
         (results (sage--parse-results json)))
    (if (null results)
        (message "sage: no results for: %s" query)
      (let* ((candidates (mapcar #'sage--create-candidate results))
             (sage--current-candidates candidates)
             (table
              (lambda (str pred action)
                (if (eq action 'metadata)
                    '(metadata (category . sage-result))
                  (complete-with-action action (mapcar #'car candidates) str pred))))
             (overlay nil)
             (state
              (lambda (action candidate)
                (when overlay
                  (delete-overlay overlay)
                  (setq overlay nil))
                (when-let (r (and candidate
                                  (cdr (assoc candidate candidates))))
                  (let* ((file (plist-get r :file))
                         (text (plist-get r :text))
                         (buf  (find-file-noselect file)))
                    (cond
                     ((eq action 'preview)
                      (when-let (marker (sage--text-position buf text))
                        (consult--jump marker)
                        (with-current-buffer buf
                          (let* ((beg (save-excursion
                                        (goto-char marker)
                                        (beginning-of-line)
                                        (point)))
                                 (fin (save-excursion
                                        (goto-char marker)
                                        (forward-line
                                         (1- (length (split-string text "\n"))))
                                        (end-of-line)
                                        (point))))
                            (setq overlay (make-overlay beg fin))
                            (overlay-put overlay 'line-prefix
                                         (propertize " " 'display
                                                     '(left-fringe sage-range-bar
                                                       font-lock-keyword-face)))))))
                     ((eq action 'return)
                      (find-file file)
                      (when-let (marker (sage--text-position (current-buffer) text))
                        (goto-char marker)
                        (recenter)))))))))
        (ignore
         (consult--read
          table
          :prompt        (format "sage (%s): " query)
          :history       'sage-search-history
          :require-match t
          :sort          nil
          :category      'sage-result
          :state         state))))))

;;; Index runner --------------------------------------------------------

(defun sage--run-index (index-args)
  "Run `sage index INDEX-ARGS' asynchronously, streaming to *sage-index*."
  (let* ((cmd (append (list sage-cli-command "index") index-args))
         (buf (get-buffer-create "*sage-index*")))
    (with-current-buffer buf
      (read-only-mode -1)
      (erase-buffer)
      (insert (format "$ %s\n\n" (mapconcat #'identity cmd " "))))
    (display-buffer buf)
    (make-process
     :name     "sage-index"
     :buffer   buf
     :command  cmd
     :sentinel (lambda (_proc event)
                 (when (string-match-p "finished" event)
                   (with-current-buffer buf
                     (goto-char (point-max))
                     (insert "\n── done ──"))
                   (message "sage: indexing complete."))))))

;;; Interactive commands ------------------------------------------------

;;;###autoload
(defun sage-search (query)
  "Search all configured knowledge bases for QUERY.
For full CLI flag control, use `sage-dispatch' instead."
  (interactive "sSearch query: ")
  (sage--do-search query (sage--build-search-args nil)))

;;;###autoload
(defun sage-search-kb (query kb)
  "Search knowledge base KB for QUERY, with completion over configured KB names."
  (interactive
   (let* ((kbs   (or (sage--list-kb-names)
                     (user-error "Sage: could not retrieve KB list")))
          (query (read-string "Search query: " nil 'sage-search-history))
          (kb    (completing-read "Knowledge base: " kbs nil t)))
     (list query kb)))
  (sage--do-search query (sage--build-search-args (list (concat "--kb=" kb)))))

;;;###autoload
(defun sage-index (&optional kb force)
  "Index knowledge bases with sage, streaming output to *sage-index*.
With FORCE, force full re-index ignoring cache.
KB, if non-nil, limits indexing to that named knowledge base."
  (interactive (list nil current-prefix-arg))
  (sage--run-index (sage--build-index-args nil kb force)))

;;; Transient -----------------------------------------------------------

(transient-define-infix sage--infix-kb ()
  "Transient infix for --kb= with completion over configured KB names."
  :description "Knowledge base"
  :class        'transient-option
  :shortarg     "-k"
  :argument     "--kb="
  :reader       (lambda (prompt initial-input history)
                  (let ((kbs (sage--list-kb-names)))
                    (if kbs
                        (completing-read prompt kbs nil nil initial-input history)
                      (read-string prompt initial-input history)))))

;;;###autoload
(transient-define-prefix sage-dispatch ()
  "Sage knowledge base search and index with full CLI flag control."
  ["Search options"
   ("-n" "Results"        "--top-k="
    :reader (lambda (prompt _ _)
              (number-to-string (read-number prompt sage-default-top-k))))
   ("-H" "Dense-only"    "--no-hybrid")
   ("-t" "Filter type"   "--filter-type=")
   ("-s" "Filter status" "--filter-status=")]
  ["Index options"
   ("-F" "Force re-index" "--force")]
  ["Common"
   (sage--infix-kb)
   ("-c" "Config file"    "--config="
    :reader (lambda (prompt _ _)
              (read-file-name prompt nil sage-config-file t)))]
  [["Search"
    ("s" "All KBs"  sage--transient-search)
    ("k" "In KB"    sage--transient-search-kb)]
   ["Other"
    ("i" "Index"    sage--transient-index)]])

(defun sage--transient-search ()
  "Search all KBs using options from `sage-dispatch'."
  (interactive)
  (let* ((targs (transient-args 'sage-dispatch))
         (args  (sage--build-search-args targs))
         (query (read-string "Search query: " nil 'sage-search-history)))
    (sage--do-search query args)))

(defun sage--transient-search-kb ()
  "Search a specific KB using options from `sage-dispatch'.
Uses --kb= from the transient if set; otherwise prompts with completion."
  (interactive)
  (let* ((targs  (transient-args 'sage-dispatch))
         (kb     (or (sage--targ-get targs "--kb=")
                     (let ((kbs (or (sage--list-kb-names)
                                    (user-error "Sage: could not retrieve KB list"))))
                       (completing-read "Knowledge base: " kbs nil t))))
         ;; Ensure exactly one --kb= in the args we pass down
         (targs* (cons (concat "--kb=" kb)
                       (cl-remove-if (lambda (a) (string-prefix-p "--kb=" a)) targs)))
         (args   (sage--build-search-args targs*))
         (query  (read-string "Search query: " nil 'sage-search-history)))
    (sage--do-search query args)))

(defun sage--transient-index ()
  "Index using options from `sage-dispatch'."
  (interactive)
  (let* ((targs (transient-args 'sage-dispatch))
         (kb    (sage--targ-get targs "--kb="))
         (force (member "--force" targs)))
    (sage--run-index (sage--build-index-args targs kb force))))

(provide 'sage)

;;; sage.el ends here
