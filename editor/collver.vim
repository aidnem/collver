" Vim syntax file
" Language: Collver

" Usage Instructions
" Put this file in .vim/syntax/collver.vim
" and add in your .vimrc file the next line:
" autocmd BufRead,BufNewFile *.collver set filetype=collver

if exists("b:current_syntax")
  finish
endif

set iskeyword=a-z,A-Z,_,!,@
syntax keyword collverTodos TODO FIXME NOTE

" Language keywords
syntax keyword collverKeywords proc memory const include alias end
syntax keyword collverControlFlow if elif else while do

" Intrinsic words
syntax keyword collverIntrinsics + - * / % = != > < >= <= << >> dup drop !8 @8 !64 @64 alloc free

" Comments
syntax region collverCommentLine start="//" end="$"   contains=collverTodos

" String literals
syntax region collverString start=/\v"/ skip=/\v\\./ end=/\v"/ contains=collverEscapes

" Escape literals \n, \r, ....
syntax match collverEscapes display contained "\\[nr\"']"

" Number literals
syntax region collverNumber start=/\s\d/ skip=/\d/ end=/\s/

" Set highlights
highlight default link collverTodos Todo
highlight default link collverKeywords Keyword
highlight default link collverControlFlow Conditional
highlight default link collverPreProc PreProc
highlight default link collverIntrinsics Operator
highlight default link collverCommentLine Comment
highlight default link collverString String
highlight default link collverNumber Number
highlight default link collverTypeNames Type
highlight default link collverChar Character
highlight default link collverEscapes SpecialChar

let b:current_syntax = "collver"

