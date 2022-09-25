@stack = global [1024 x i64] undef
@sp    = global i64 0
define void @push(i64 %val) {
  %sp = load i64, i64* @sp
  %addr = getelementptr [1024 x i64], [1024 x i64]* @stack, i64 0, i64 %sp
  store i64 %val, i64* %addr
  %newsp = add i64 %sp, 1
  store i64 %newsp, i64* @sp
  ret void
}

define i64 @pop() {
  %sp = load i64, i64* @sp
  %topsp = sub i64 %sp, 1
  %addr = getelementptr [1024 x i64], [1024 x i64]* @stack, i64 0, i64 %topsp
  %val = load i64, i64* %addr
  store i64 %topsp, i64* @sp
  ret i64 %val
}

define void @proc_intrinsic_plus() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = add i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_minus() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = sub i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_mult() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = mul i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_div() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = sdiv i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_mod() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = srem i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_eq() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp eq i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_ne() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp ne i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_gt() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp sgt i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_lt() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp slt i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_ge() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp sge i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_le() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c_i1 = icmp sle i64 %b, %a
  %c = zext i1 %c_i1 to i64
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_shl() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = shl i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_shr() {
  %a = call i64() @pop()
  %b = call i64() @pop()
  %c = lshr i64 %b, %a
  call void(i64) @push(i64 %c)
  ret void
}

define void @proc_intrinsic_drop() {
  call i64() @pop()
  ret void
}

declare i64 @printf(i8*, ...)
@fmt = unnamed_addr constant [4 x i8] c"%i\0A\00"
define void @proc_intrinsic_print() {
  %fmtptr = getelementptr [4 x i8], [4 x i8]* @fmt, i64 0, i64 0
  %a = call i64() @pop()
  call i64(i8*, ...) @printf(i8* %fmtptr, i64 %a)
  ret void
}

define void @proc_intrinsic_dup() {
  %a = call i64() @pop()
  call void(i64) @push(i64 %a)
  call void(i64) @push(i64 %a)
  ret void
}

@intrinsic_puts_fmt = private unnamed_addr constant [3 x i8] c"%s\00"
define void @proc_intrinsic_puts() {
  %str_int = call i64() @pop()
  %str_ptr = inttoptr i64 %str_int to ptr
  call i64(i8*, ...) @printf(i8* @intrinsic_puts_fmt, ptr %str_ptr)
  ret void
}

define void @proc_intrinsic_store8() {
  %ptr_int = call i64() @pop()
  %a = call i64() @pop()
  %a_trunc = trunc i64 %a to i8
  %ptr_ = inttoptr i64 %ptr_int to ptr
  store i8 %a_trunc, ptr %ptr_
  ret void
}

define void @proc_intrinsic_load8() {
  %ptr_int = call i64() @pop()
  %ptr_ = inttoptr i64 %ptr_int to ptr
  %c_i8 = load i8, ptr %ptr_
  %c_i64 = zext i8 %c_i8 to i64
  call void(i64) @push(i64 %c_i64)
  ret void
}

define void @proc_intrinsic_store64() {
  %ptr_int = call i64() @pop()
  %a = call i64() @pop()
  %ptr_ = inttoptr i64 %ptr_int to ptr
  store i64 %a, ptr %ptr_
  ret void
}

define void @proc_intrinsic_load64() {
  %ptr_int = call i64 @pop()
  %ptr_ = inttoptr i64 %ptr_int to ptr
  %c_i64 = load i64, ptr %ptr_
  call void(i64) @push(i64 %c_i64)
  ret void
}

declare noalias ptr @malloc(i64 noundef)
define void @proc_intrinsic_alloc() {
  %size = call i64() @pop()
  %ptr_ = call ptr @malloc(i64 %size)
  %ptr_int = ptrtoint ptr %ptr_ to i64
  call void(i64) @push(i64 %ptr_int)
  ret void
}

declare void @free(ptr noundef)
define void @proc_intrinsic_free() {
  %int_ = call i64() @pop()
  %ptr_ = inttoptr i64 %int_ to ptr
  call void @free(ptr %ptr_)
  ret void
}

declare void @exit(i32 noundef)
define void @proc_intrinsic_exit() {
  %ec_i64 = call i64() @pop()
  %ec_i32 = trunc i64 %ec_i64 to i32
  call void @exit(i32 noundef %ec_i32) noreturn
  unreachable
}

declare ptr @__error()
define void @proc_intrinsic_check_errno() {
  %errno_ptr = call ptr @__error()
  %errno_i32 = load i32, ptr %errno_ptr
  %errno_i64 = zext i32 %errno_i32 to i64
  call void @push(i64 %errno_i64)
  ret void
}
